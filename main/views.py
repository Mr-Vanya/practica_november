from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.shortcuts import render

from .models import Category, Product


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


def help_page(request):
    return render(request, "main/help.html")


def login_view(request):
    # На этом этапе форма только принимает значения и остаётся на этой же странице.
    submitted = request.method == "POST"
    return render(request, "main/login.html", {"submitted": submitted})
