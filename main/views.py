import csv
import hashlib
import io
import json
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.db import IntegrityError, transaction
from django.db.models import Avg, F, Q, Sum, Count, IntegerField, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Cart, CartAddSubmission, CartItem, Category, CustomerOrder, Manufacturer, OrderItem, OrderStatus,
    Notification, Product, Review, Stock,
)

auth_logger = logging.getLogger("main.auth")
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_PAIR_LIMIT = 5
LOGIN_IP_LIMIT = 20


def _login_throttle_key(scope, ip_address, username=""):
    raw_key = f"{scope}:{ip_address}:{username}".encode("utf-8")
    return "login-throttle:" + hashlib.sha256(raw_key).hexdigest()


def _login_is_blocked(ip_address, username):
    now = timezone.now().timestamp()
    keys = (
        _login_throttle_key("pair-lock", ip_address, username),
        _login_throttle_key("ip-lock", ip_address),
    )
    return any((cache.get(key) or 0) > now for key in keys)


def _record_failed_login(ip_address, username):
    limits = (
        ("pair", username, LOGIN_PAIR_LIMIT),
        ("ip", "", LOGIN_IP_LIMIT),
    )
    now = timezone.now().timestamp()
    blocked = False
    for scope, value, limit in limits:
        attempts_key = _login_throttle_key(f"{scope}-attempts", ip_address, value)
        attempts = cache.get(attempts_key, 0) + 1
        if attempts >= limit:
            lock_key = _login_throttle_key(f"{scope}-lock", ip_address, value)
            cache.set(lock_key, now + LOGIN_LOCK_SECONDS, timeout=LOGIN_LOCK_SECONDS)
            cache.delete(attempts_key)
            blocked = True
        else:
            cache.set(attempts_key, attempts, timeout=LOGIN_WINDOW_SECONDS)
    return blocked


def _create_order_notification(order, title, message):
    Notification.objects.create(
        user=order.user, order=order, title=title, message=message
    )


def home(request):
    products = Product.objects.filter(is_active=True).select_related("category", "manufacturer", "stock")[:8]
    return render(request, "main/home.html", {"products": products})


def catalog(request):
    qs = Product.objects.filter(is_active=True).select_related("category", "manufacturer", "stock").annotate(rating=Avg("reviews__rating"))
    query = request.GET.get("q", "").strip()
    categories_selected = request.GET.getlist("category")
    manufacturer_options = Manufacturer.objects.filter(products__is_active=True).distinct().order_by("name")
    manufacturer_ids = set(manufacturer_options.values_list("id", flat=True))
    selected_manufacturers = [int(value) for value in request.GET.getlist("manufacturer") if value.isdigit() and int(value) in manufacturer_ids]
    language_options = sorted({
        value.strip().lower()
        for value in Product.objects.filter(is_active=True).exclude(language="").values_list("language", flat=True)
        if value.strip()
    })
    selected_languages = [
        value.strip().lower()
        for value in request.GET.getlist("language")
        if value.strip().lower() in language_options
    ]
    age_options = list(Product.objects.filter(is_active=True).values_list("min_age", flat=True).distinct().order_by("min_age"))
    selected_ages = [int(age) for age in request.GET.getlist("age") if age.isdigit() and int(age) in age_options]
    duration_options = list(Product.objects.filter(is_active=True, duration_min__isnull=False).values_list("duration_min", flat=True).distinct().order_by("duration_min"))
    selected_durations = [int(value) for value in request.GET.getlist("duration") if value.isdigit() and int(value) in duration_options]
    player_ranges = Product.objects.filter(is_active=True).values_list("min_players", "max_players")
    player_options = sorted({count for minimum, maximum in player_ranges for count in range(minimum, maximum + 1)})
    selected_players = [int(value) for value in request.GET.getlist("players") if value.isdigit() and int(value) in player_options]
    if query:
        qs = qs.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )
    if categories_selected: qs = qs.filter(category__slug__in=categories_selected)
    if selected_manufacturers: qs = qs.filter(manufacturer_id__in=selected_manufacturers)
    if selected_languages:
        language_query = Q()
        for language in selected_languages:
            language_query |= Q(language__iexact=language)
        qs = qs.filter(language_query)
    if selected_ages: qs = qs.filter(min_age__in=selected_ages)
    if selected_durations: qs = qs.filter(duration_min__in=selected_durations)
    if selected_players:
        player_query = Q()
        for count in selected_players:
            player_query |= Q(min_players__lte=count, max_players__gte=count)
        qs = qs.filter(player_query)
    if request.GET.get("in_stock"): qs = qs.filter(stock__quantity__gt=0)
    min_price_value = request.GET.get("min_price", "").strip()
    max_price_value = request.GET.get("max_price", "").strip()
    if min_price_value or max_price_value:
        try:
            min_price = Decimal(min_price_value) if min_price_value else None
            max_price = Decimal(max_price_value) if max_price_value else None
            if (min_price is not None and min_price < 0) or (max_price is not None and max_price < 0):
                messages.error(request, "Цена не может быть отрицательной.")
            elif min_price is not None and max_price is not None and min_price > max_price:
                messages.error(request, "Цена «от» не может быть выше цены «до».")
            else:
                if min_price is not None:
                    qs = qs.filter(price__gte=min_price)
                if max_price is not None:
                    qs = qs.filter(price__lte=max_price)
        except Exception:
            messages.error(request, "Введите корректную цену.")
    order = request.GET.get("sort")
    if order in {"price", "-price", "name", "-rating"}: qs = qs.order_by(order)
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(request, "main/catalog.html", {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "query": query,
        "selected_categories": categories_selected,
        "manufacturer_options": manufacturer_options,
        "selected_manufacturers": selected_manufacturers,
        "language_options": language_options,
        "selected_languages": selected_languages,
        "age_options": age_options,
        "selected_ages": selected_ages,
        "duration_options": duration_options,
        "selected_durations": selected_durations,
        "player_options": player_options,
        "selected_players": selected_players,
        "selected_sort": order or "name",
        "query_string": query_params.urlencode(),
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product.objects.select_related("category", "manufacturer", "stock").annotate(rating=Avg("reviews__rating")), pk=product_id, is_active=True)
    reviews = product.reviews.select_related("user")
    if request.method == "POST":
        if not request.user.is_authenticated: return redirect("main:login")
        rating = request.POST.get("rating", "")
        body = request.POST.get("body", "").strip()
        try:
            rating = int(rating)
            if rating not in range(1, 6): raise ValueError
            Review.objects.update_or_create(user=request.user, product=product, defaults={"rating": rating, "body": body})
            messages.success(request, "Отзыв сохранён.")
        except (ValueError, TypeError): messages.error(request, "Оценка должна быть от 1 до 5.")
        return redirect("main:product_detail", product_id=product.pk)
    return render(request, "main/product_detail.html", {
        "product": product,
        "reviews": reviews,
        "cart_add_token": uuid.uuid4(),
    })


def _user_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def cart_detail(request):
    cart = _user_cart(request.user)
    items = list(cart.items.select_related("product", "product__stock"))
    total = Decimal("0.00")
    for item in items:
        item.line_total = item.product.price * item.quantity
        total += item.line_total
    return render(request, "main/cart.html", {"cart": cart, "items": items, "total": total})


@login_required
@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    cart = _user_cart(request.user)
    try:
        token = uuid.UUID(request.POST.get("cart_add_token", ""))
    except (TypeError, ValueError, AttributeError):
        messages.error(request, "Форма устарела. Откройте карточку товара и попробуйте ещё раз.")
        return redirect("main:product_detail", product_id=product.pk)

    with transaction.atomic():
        submission, created = CartAddSubmission.objects.get_or_create(
            token=token,
            defaults={"cart": cart, "product": product},
        )
        if submission.cart_id != cart.pk or submission.product_id != product.pk:
            messages.error(request, "Не удалось проверить отправку. Обновите карточку товара.")
        elif not created:
            messages.info(request, "Эта отправка уже обработана; товар не добавлен повторно.")
        else:
            item, item_created = CartItem.objects.get_or_create(
                cart=cart, product=product, defaults={"quantity": 1}
            )
            if not item_created:
                item.quantity = F("quantity") + 1
                item.save(update_fields=["quantity"])
            messages.success(request, "Товар добавлен в корзину.")
    return redirect(request.POST.get("next") or "main:cart")


@login_required
@require_POST
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    action = request.POST.get("action")
    if action == "remove":
        item.delete()
        return redirect("main:cart")

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    item.quantity = min(max(quantity, 1), 99)
    item.save(update_fields=["quantity"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        cart_items = CartItem.objects.filter(cart=item.cart).select_related("product")
        cart_total = sum(
            (cart_item.product.price * cart_item.quantity for cart_item in cart_items),
            Decimal("0.00"),
        )
        return JsonResponse({
            "quantity": item.quantity,
            "line_total": str(item.product.price * item.quantity),
            "cart_total": str(cart_total),
        })

    return redirect("main:cart")


@login_required
def checkout(request):
    cart = _user_cart(request.user)
    items = list(cart.items.select_related("product").prefetch_related("product__stock"))
    checkout_token = None
    if request.method == "POST":
        try:
            checkout_token = uuid.UUID(request.POST.get("checkout_token", ""))
        except (TypeError, ValueError, AttributeError):
            checkout_token = None

        if checkout_token is None:
            messages.error(request, "Форма устарела. Обновите страницу и попробуйте ещё раз.")
        else:
            existing_order = CustomerOrder.objects.filter(checkout_token=checkout_token).first()
            if existing_order and existing_order.user_id == request.user.id:
                return redirect("main:order_detail", order_id=existing_order.pk)
            if existing_order:
                checkout_token = None
                messages.error(request, "Не удалось проверить отправку формы. Обновите страницу.")

        required = ["contact_name", "phone", "email", "pickup_point"]
        if checkout_token is None:
            pass
        elif not all(request.POST.get(k, "").strip() for k in required):
            messages.error(request, "Заполните все контактные поля.")
        elif not items:
            messages.error(request, "Корзина пуста.")
        else:
            try:
                with transaction.atomic():
                    total = Decimal("0.00")
                    locked = []
                    for item in items:
                        stock = Stock.objects.select_for_update().get(product=item.product)
                        if item.quantity > stock.quantity:
                            raise ValueError(f"Недостаточно товара «{item.product.name}»: доступно {stock.quantity}.")
                        total += item.product.price * item.quantity
                        locked.append((item, stock))
                    status, _ = OrderStatus.objects.get_or_create(name="Новый")
                    order = CustomerOrder.objects.create(
                        number="ORD-" + uuid.uuid4().hex[:8].upper(), checkout_token=checkout_token,
                        user=request.user, status=status, total=total,
                        contact_name=request.POST["contact_name"].strip(), phone=request.POST["phone"].strip(),
                        email=request.POST["email"].strip(), pickup_point=request.POST["pickup_point"].strip())
                    _create_order_notification(
                        order,
                        "Заказ создан",
                        f"Заказ {order.number} оформлен. Текущий статус: {order.status.name}.",
                    )
                    for item, stock in locked:
                        OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, unit_price=item.product.price)
                        stock.quantity -= item.quantity; stock.save(update_fields=["quantity"])
                    cart.items.all().delete()
                messages.success(request, f"Заказ {order.number} создан.")
                return redirect("main:order_detail", order_id=order.pk)
            except Stock.DoesNotExist: messages.error(request, "Для одного из товаров не настроен складской остаток.")
            except ValueError as exc: messages.error(request, str(exc))
            except IntegrityError:
                existing_order = CustomerOrder.objects.filter(checkout_token=checkout_token, user=request.user).first()
                if existing_order:
                    return redirect("main:order_detail", order_id=existing_order.pk)
                messages.error(request, "Не удалось оформить заказ. Обновите страницу и попробуйте снова.")
    if checkout_token is None:
        checkout_token = uuid.uuid4()
    total = sum((i.product.price * i.quantity for i in items), Decimal("0.00"))
    return render(request, "main/checkout.html", {"items": items, "total": total, "checkout_token": checkout_token})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        username_key = " ".join(username.strip().casefold().split())[:150]
        ip_address = request.META.get("REMOTE_ADDR", "unknown")

        if _login_is_blocked(ip_address, username_key):
            auth_logger.warning(
                "Login blocked by throttle: username=%r ip=%s",
                username_key,
                ip_address,
            )
            messages.error(request, "Слишком много попыток входа. Попробуйте снова через 15 минут.")
            return render(request, "main/login.html", status=429)

        user = authenticate(
            request,
            username=username,
            password=request.POST.get("password", ""),
        )
        if user is not None:
            cache.delete(_login_throttle_key("pair-attempts", ip_address, username_key))
            cache.delete(_login_throttle_key("pair-lock", ip_address, username_key))
            login(request, user); return redirect(request.GET.get("next") or "main:home")
        locked = _record_failed_login(ip_address, username_key)
        auth_logger.warning(
            "Failed login attempt: username=%r ip=%s blocked=%s",
            username_key,
            ip_address,
            locked,
        )
        if locked:
            messages.error(request, "Слишком много попыток входа. Попробуйте снова через 15 минут.")
            return render(request, "main/login.html", status=429)
        messages.error(request, "Не удалось войти: проверьте логин и пароль.")
    return render(request, "main/login.html")


def register_view(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(); login(request, user); return redirect("main:home")
    return render(request, "main/register.html", {"form": form})


def page_not_found(request, exception):
    return render(request, "main/404.html", status=404)


@login_required
def logout_view(request):
    if request.method == "POST": logout(request)
    return redirect("main:home")


@login_required
def order_list(request):
    orders = CustomerOrder.objects.filter(user=request.user).select_related("status")
    return render(request, "main/orders.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(CustomerOrder.objects.select_related("status").prefetch_related("items__product"), pk=order_id, user=request.user)
    return render(request, "main/order_detail.html", {"order": order})


@login_required
def order_export_csv(request, order_id):
    order_query = CustomerOrder.objects.select_related("status", "user").prefetch_related("items__product")
    if request.user.is_staff or request.user.groups.filter(name="Менеджер").exists():
        order = get_object_or_404(order_query, pk=order_id)
    else:
        order = get_object_or_404(order_query, pk=order_id, user=request.user)

    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Номер заказа", "Дата", "Статус", "Получатель", "Телефон",
        "Электронная почта", "Пункт выдачи", "Товар", "Количество",
        "Цена за единицу, ₽", "Сумма позиции, ₽",
    ])

    def safe_cell(value):
        text = str(value if value is not None else "")
        if text.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text
        return text

    order_date = timezone.localtime(order.created_at).strftime("%d.%m.%Y %H:%M")
    for item in order.items.all():
        writer.writerow([
            safe_cell(order.number), order_date, safe_cell(order.status.name),
            safe_cell(order.contact_name), safe_cell(order.phone), safe_cell(order.email),
            safe_cell(order.pickup_point), safe_cell(item.product.name), item.quantity,
            str(item.unit_price), str(item.unit_price * item.quantity),
        ])
    writer.writerow(["", "", "", "", "", "", "", "ИТОГО", "", "", str(order.total)])

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="order_{order.number}.csv"'
    return response


@login_required
@require_POST
def order_cancel(request, order_id):
    with transaction.atomic():
        order = get_object_or_404(CustomerOrder.objects.select_for_update(), pk=order_id, user=request.user)
        if order.status.name in {"Отменён", "Завершён"}: messages.error(request, "Этот заказ нельзя отменить.")
        else:
            for item in order.items.select_related("product"):
                stock, _ = Stock.objects.select_for_update().get_or_create(product=item.product)
                stock.quantity += item.quantity; stock.save(update_fields=["quantity"])
            order.status, _ = OrderStatus.objects.get_or_create(name="Отменён")
            order.save(update_fields=["status"])
            _create_order_notification(order, "Статус заказа изменён", f"Заказ {order.number} отменён.")
            messages.success(request, "Заказ отменён, остаток возвращён.")
    return redirect("main:order_detail", order_id=order_id)


@login_required
@require_POST
def order_return_request(request, order_id):
    reason = request.POST.get("reason", "").strip()
    try:
        product_id = int(request.POST.get("return_product", ""))
        return_quantity = int(request.POST.get("return_quantity", ""))
    except (TypeError, ValueError):
        product_id = None
        return_quantity = 0
    with transaction.atomic():
        order = get_object_or_404(
            CustomerOrder.objects.select_for_update(), pk=order_id, user=request.user
        )
        if order.status.name != "Завершён":
            messages.error(request, "Оформить возврат можно после завершения заказа.")
        elif order.return_status == "pending":
            messages.info(request, "Заявка на возврат уже ожидает решения менеджера.")
        elif order.return_status == "approved":
            messages.info(request, "Возврат по этому заказу уже одобрен.")
        elif not reason:
            messages.error(request, "Укажите причину возврата.")
        else:
            order_item = order.items.select_for_update().filter(product_id=product_id).select_related("product").first() if product_id else None
            if order_item is None:
                messages.error(request, "Выберите товар из этого заказа.")
            elif return_quantity < 1 or return_quantity > order_item.quantity:
                messages.error(request, f"Количество для возврата должно быть от 1 до {order_item.quantity}.")
            else:
                order.return_reason = reason[:1000]
                order.return_product = order_item.product
                order.return_quantity = return_quantity
                order.return_status = "pending"
                order.save(update_fields=["return_reason", "return_product", "return_quantity", "return_status"])
                _create_order_notification(
                    order,
                    "Заявка на возврат отправлена",
                    f"Заявка на возврат заказа {order.number} ({order_item.product.name}, {return_quantity} шт.) отправлена и ожидает решения менеджера.",
                )
                messages.success(
                    request,
                    "Заявка на возврат оформлена. Дождитесь решения менеджера.",
                )
    return redirect("main:order_detail", order_id=order_id)


def help_page(request):
    return render(request, "main/help.html", {
        "categories": Category.objects.all(),
        "manufacturers": Manufacturer.objects.filter(products__is_active=True).distinct().order_by("name"),
        "age_options": Product.objects.filter(is_active=True).values_list("min_age", flat=True).distinct().order_by("min_age"),
        "player_options": sorted({n for low, high in Product.objects.filter(is_active=True).values_list("min_players", "max_players") for n in range(low, high + 1)}),
        "duration_options": Product.objects.filter(is_active=True, duration_min__isnull=False).values_list("duration_min", flat=True).distinct().order_by("duration_min"),
    })


def rules_help_page(request):
    return render(request, "main/rules_help.html")


def manager_required(user): return user.is_authenticated and (user.is_staff or user.groups.filter(name="Менеджер").exists())


@user_passes_test(manager_required)
def manager_products(request):
    if request.method == "POST":
        product = get_object_or_404(Product, pk=request.POST.get("product_id"))
        action = request.POST.get("action")
        if action == "stock":
            try:
                quantity = int(request.POST.get("quantity", ""))
                if quantity < 0:
                    raise ValueError
            except (TypeError, ValueError):
                messages.error(request, "Остаток должен быть целым числом не меньше нуля.")
            else:
                Stock.objects.update_or_create(product=product, defaults={"quantity": quantity})
                messages.success(request, f"Остаток товара «{product.name}» обновлён.")
        elif action == "delete":
            product_name = product.name
            try:
                product.delete()
                messages.success(request, f"Товар «{product_name}» удалён.")
            except ProtectedError:
                product.is_active = False
                product.save(update_fields=["is_active"])
                messages.warning(request, f"Товар «{product_name}» уже связан с заказом или корзиной, поэтому скрыт из каталога; история сохранена.")
        return redirect("main:manager_products")

    products = Product.objects.select_related("category", "manufacturer", "stock")
    return render(request, "main/manager_products.html", {"products": products})


@user_passes_test(manager_required)
def manager_product_create(request):
    from .forms import ProductForm
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(); Stock.objects.get_or_create(product=product); messages.success(request, "Товар добавлен."); return redirect("main:manager_products")
    return render(request, "main/manager_product_form.html", {"form": form})


@user_passes_test(manager_required)
def manager_product_edit(request, product_id):
    from .forms import ProductForm
    product = get_object_or_404(Product, pk=product_id)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Изменения товара «{product.name}» сохранены.")
        return redirect("main:manager_products")
    return render(request, "main/manager_product_form.html", {"form": form, "product": product, "is_edit": True})


@user_passes_test(manager_required)
def manager_orders(request):
    statuses = ["Новый", "Подтверждён", "Собран", "Подготовлен к выдаче", "Завершён", "Отменён"]
    if request.method == "POST":
        with transaction.atomic():
            order = get_object_or_404(CustomerOrder.objects.select_for_update(), pk=request.POST.get("order_id"))
            new_status = request.POST.get("status", "")
            if new_status not in statuses:
                messages.error(request, "Выберите статус из списка.")
                return redirect("main:manager_orders")
            old_status = order.status.name
            if new_status == "Отменён" and order.status.name != "Отменён":
                for item in order.items.select_related("product"):
                    stock, _ = Stock.objects.select_for_update().get_or_create(product=item.product)
                    stock.quantity += item.quantity; stock.save(update_fields=["quantity"])
            status, _ = OrderStatus.objects.get_or_create(name=new_status)
            order.status = status; order.save(update_fields=["status"])
            if old_status != new_status:
                _create_order_notification(
                    order,
                    "Статус заказа изменён",
                    f"Статус заказа {order.number} изменён: «{old_status}» → «{new_status}».",
                )
        messages.success(request, "Статус заказа обновлён.")
        return redirect("main:manager_orders")
    return render(request, "main/manager_orders.html", {
        "orders": CustomerOrder.objects.select_related("user", "status"),
        "statuses": statuses,
    })


@user_passes_test(manager_required)
@require_POST
def manager_return_decision(request, order_id):
    decision = request.POST.get("decision")
    if decision not in {"approved", "rejected"}:
        messages.error(request, "Неизвестное решение по возврату.")
        return redirect("main:manager_orders")

    with transaction.atomic():
        order = get_object_or_404(CustomerOrder.objects.select_for_update(), pk=order_id)
        if order.return_status != "pending":
            messages.error(request, "По этому заказу нет возврата, ожидающего решения.")
        else:
            order.return_status = decision
            order.save(update_fields=["return_status"])
            decision_text = "одобрена" if decision == "approved" else "отклонена"
            _create_order_notification(
                order,
                "Решение по возврату",
                f"Заявка на возврат заказа {order.number} {decision_text} менеджером.",
            )
            messages.success(
                request,
                "Возврат одобрен." if decision == "approved" else "Возврат отклонён.",
            )
    return redirect("main:manager_orders")


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).select_related("order")
    return render(request, "main/notifications.html", {"notifications": notifications})


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    if notification.order_id:
        return redirect("main:order_detail", order_id=notification.order_id)
    return redirect("main:notifications")


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("main:notifications")


@user_passes_test(manager_required)
def manager_statistics(request):
    orders = CustomerOrder.objects.exclude(status__name="Отменён")
    revenue = orders.aggregate(value=Sum("total"))["value"] or Decimal("0.00")

    order_status_rows = list(
        CustomerOrder.objects.values("status__name")
        .annotate(value=Count("id"))
        .order_by("status__name")
    )
    category_rows = list(
        Product.objects.values("category__name")
        .annotate(value=Count("id"))
        .order_by("-value", "category__name")
    )
    inventory_rows = list(
        Product.objects.select_related("category", "manufacturer")
        .annotate(stock_quantity=Coalesce("stock__quantity", Value(0), output_field=IntegerField()))
        .order_by("stock_quantity", "name")
    )
    low_stock_products = [
        {"product__name": product.name, "quantity": product.stock_quantity}
        for product in inventory_rows if product.stock_quantity <= 3
    ]
    low_stock_count = len(low_stock_products)

    month_names = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    today = timezone.localdate()
    month_index = today.year * 12 + today.month - 1
    month_keys = []
    for offset in range(5, -1, -1):
        year, month_zero_based = divmod(month_index - offset, 12)
        month = month_zero_based + 1
        month_keys.append((year, month, f"{month_names[month_zero_based]} {year}"))

    revenue_by_month = {
        (row["month"].year, row["month"].month): row["value"]
        for row in orders.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(value=Sum("total"))
    }
    revenue_month_rows = [
        {"label": label, "value": revenue_by_month.get((year, month), Decimal("0.00"))}
        for year, month, label in month_keys
    ]

    def make_bars(rows, label_field, value_field="value"):
        maximum = max((row[value_field] for row in rows), default=0) or 1
        return [
            {
                "label": row[label_field],
                "value": row[value_field],
                "width": max(3, round(float(row[value_field]) / float(maximum) * 100)) if row[value_field] else 0,
            }
            for row in rows
        ]

    status_bars = make_bars(order_status_rows, "status__name")
    category_bars = make_bars(category_rows, "category__name")
    revenue_bars = make_bars(revenue_month_rows, "label")
    stock_bars = make_bars(low_stock_products, "product__name", "quantity")
    recent_orders = CustomerOrder.objects.select_related("user", "status").order_by("-created_at")[:20]

    return render(request, "main/manager_statistics.html", {
        "order_count": CustomerOrder.objects.count(),
        "revenue": revenue,
        "product_count": Product.objects.count(),
        "low_stock": low_stock_count,
        "order_status_bars": status_bars,
        "revenue_bars": revenue_bars,
        "category_bars": category_bars,
        "stock_bars": stock_bars[:10],
        "inventory_rows": inventory_rows,
        "recent_orders": recent_orders,
        "category_rows": category_rows,
        "revenue_month_rows": revenue_month_rows,
    })


@require_GET
def catalog_json(request):
    products = Product.objects.filter(is_active=True).select_related(
        "category", "manufacturer", "stock"
    ).annotate(rating=Avg("reviews__rating"))

    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    categories = [value for value in request.GET.getlist("category") if value]
    if categories:
        products = products.filter(category__slug__in=categories)

    manufacturers = [
        int(value) for value in request.GET.getlist("manufacturer") if value.isdigit()
    ]
    if manufacturers:
        products = products.filter(manufacturer_id__in=manufacturers)

    languages = [value.strip() for value in request.GET.getlist("language") if value.strip()]
    if languages:
        language_query = Q()
        for language in languages:
            language_query |= Q(language__iexact=language)
        products = products.filter(language_query)

    ages = [int(value) for value in request.GET.getlist("age") if value.isdigit()]
    if ages:
        products = products.filter(min_age__in=ages)

    durations = [int(value) for value in request.GET.getlist("duration") if value.isdigit()]
    if durations:
        products = products.filter(duration_min__in=durations)

    players = [int(value) for value in request.GET.getlist("players") if value.isdigit()]
    if players:
        player_query = Q()
        for count in players:
            player_query |= Q(min_players__lte=count, max_players__gte=count)
        products = products.filter(player_query)

    if request.GET.get("in_stock"):
        products = products.filter(stock__quantity__gt=0)

    min_value = request.GET.get("min_price", "").strip()
    max_value = request.GET.get("max_price", "").strip()
    try:
        min_price = Decimal(min_value) if min_value else None
        max_price = Decimal(max_value) if max_value else None
    except (InvalidOperation, ValueError):
        return JsonResponse({"error": "Введите корректную цену."}, status=400)
    if (min_price is not None and not min_price.is_finite()) or (max_price is not None and not max_price.is_finite()):
        return JsonResponse({"error": "Введите конечное числовое значение цены."}, status=400)
    if (min_price is not None and min_price < 0) or (max_price is not None and max_price < 0):
        return JsonResponse({"error": "Цена не может быть отрицательной."}, status=400)
    if min_price is not None and max_price is not None and min_price > max_price:
        return JsonResponse({"error": "Цена «от» не может быть выше цены «до»."}, status=400)
    if min_price is not None:
        products = products.filter(price__gte=min_price)
    if max_price is not None:
        products = products.filter(price__lte=max_price)

    sort = request.GET.get("sort", "name")
    if sort in {"price", "-price", "name", "-rating"}:
        products = products.order_by(sort)

    page = Paginator(products, 20).get_page(request.GET.get("page"))
    results = []
    for product in page.object_list:
        try:
            stock_quantity = product.stock.quantity
        except Stock.DoesNotExist:
            stock_quantity = 0
        results.append({
            "id": product.pk,
            "name": product.name,
            "detail_url": reverse("main:product_detail", args=[product.pk]),
            "image_url": product.image.url if product.image else "",
            "category": product.category.name,
            "min_age": product.min_age,
            "min_players": product.min_players,
            "max_players": product.max_players,
            "duration_min": product.duration_min,
            "rating": float(product.rating) if product.rating is not None else None,
            "price": str(product.price),
            "stock_quantity": stock_quantity,
        })

    return JsonResponse({
        "results": results,
        "total": page.paginator.count,
        "page": page.number,
        "num_pages": page.paginator.num_pages,
        "has_previous": page.has_previous(),
        "has_next": page.has_next(),
    })
