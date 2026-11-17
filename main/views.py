from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, CustomerOrder, Product


def home(request):
    products = Product.objects.filter(is_active=True).select_related(
        "category", "manufacturer", "stock"
    )[:8]
    return render(request, "main/home.html", {"products": products})


def catalog(request):
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category", "manufacturer", "stock")
        .annotate(rating=Avg("reviews__rating"))
    )
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        products = products.filter(category__slug=category)
    if request.GET.get("in_stock"):
        products = products.filter(stock__quantity__gt=0)
    if request.GET.get("max_price"):
        try:
            products = products.filter(price__lte=Decimal(request.GET["max_price"]))
        except Exception:
            pass
    order = request.GET.get("sort")
    if order in {"price", "-price", "name", "-rating"}:
        products = products.order_by(order)
    page_obj = Paginator(products, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "main/catalog.html",
        {
            "page_obj": page_obj,
            "categories": Category.objects.all(),
            "query": query,
            "selected_category": category,
        },
    )


def product_detail(request, product_id):
    product = get_object_or_404(
        Product.objects.select_related("category", "manufacturer", "stock")
        .annotate(rating=Avg("reviews__rating")),
        pk=product_id,
        is_active=True,
    )
    reviews = product.reviews.select_related("user")
    return render(request, "main/product_detail.html", {"product": product, "reviews": reviews})


def help_page(request):
    return render(request, "main/help.html")


def login_view(request):
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user is not None:
            login(request, user)
            return redirect(request.GET.get("next") or "main:home")
        messages.error(request, "Не удалось войти: проверьте логин и пароль.")
    return render(request, "main/login.html")


def register_view(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("main:home")
    return render(request, "main/register.html", {"form": form})

def page_not_found(request, exception):
    return render(request, 'main/404.html', status=404)


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("main:home")


@login_required
def order_list(request):
    orders = CustomerOrder.objects.filter(user=request.user).select_related("status")
    return render(request, "main/orders.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        CustomerOrder.objects.select_related("status").prefetch_related("items__product"),
        pk=order_id,
        user=request.user,
    )
    return render(request, "main/order_detail.html", {"order": order})
