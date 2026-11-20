import json
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.db import transaction
from django.db.models import Avg, F, Q, Sum, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import (
    Cart, CartItem, Category, CustomerOrder, Manufacturer, OrderItem, OrderStatus,
    Product, Review, Stock,
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
    return render(request, "main/product_detail.html", {"product": product, "reviews": reviews})


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
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": 1})
    if not created: item.quantity = F("quantity") + 1; item.save(update_fields=["quantity"])
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
    if request.method == "POST":
        required = ["contact_name", "phone", "email", "pickup_point"]
        if not all(request.POST.get(k, "").strip() for k in required):
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
                        number="ORD-" + uuid.uuid4().hex[:8].upper(), user=request.user, status=status, total=total,
                        contact_name=request.POST["contact_name"].strip(), phone=request.POST["phone"].strip(),
                        email=request.POST["email"].strip(), pickup_point=request.POST["pickup_point"].strip())
                    for item, stock in locked:
                        OrderItem.objects.create(order=order, product=item.product, quantity=item.quantity, unit_price=item.product.price)
                        stock.quantity -= item.quantity; stock.save(update_fields=["quantity"])
                    cart.items.all().delete()
                messages.success(request, f"Заказ {order.number} создан.")
                return redirect("main:order_detail", order_id=order.pk)
            except Stock.DoesNotExist: messages.error(request, "Для одного из товаров не настроен складской остаток.")
            except ValueError as exc: messages.error(request, str(exc))
    total = sum((i.product.price * i.quantity for i in items), Decimal("0.00"))
    return render(request, "main/checkout.html", {"items": items, "total": total})


def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username", ""), password=request.POST.get("password", ""))
        if user is not None:
            login(request, user); return redirect(request.GET.get("next") or "main:home")
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
            order.save(update_fields=["status"]); messages.success(request, "Заказ отменён, остаток возвращён.")
    return redirect("main:order_detail", order_id=order_id)


@login_required
@require_POST
def order_return_request(request, order_id):
    reason = request.POST.get("reason", "").strip()
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
            order.return_reason = reason[:1000]
            order.return_status = "pending"
            order.save(update_fields=["return_reason", "return_status"])
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
            if new_status == "Отменён" and order.status.name != "Отменён":
                for item in order.items.select_related("product"):
                    stock, _ = Stock.objects.select_for_update().get_or_create(product=item.product)
                    stock.quantity += item.quantity; stock.save(update_fields=["quantity"])
            status, _ = OrderStatus.objects.get_or_create(name=new_status)
            order.status = status; order.save(update_fields=["status"])
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
            messages.success(
                request,
                "Возврат одобрен." if decision == "approved" else "Возврат отклонён.",
            )
    return redirect("main:manager_orders")


@user_passes_test(manager_required)
def manager_statistics(request):
    return render(request, "main/manager_statistics.html", {
        "order_count": CustomerOrder.objects.count(),
        "revenue": CustomerOrder.objects.exclude(status__name="Отменён").aggregate(value=Sum("total"))["value"] or 0,
        "product_count": Product.objects.count(),
        "low_stock": Stock.objects.filter(quantity__lte=3).count(),
    })


def catalog_json(request):
    products = Product.objects.filter(is_active=True).values("id", "name", "price", "category__name")
    return JsonResponse({"results": list(products)})
