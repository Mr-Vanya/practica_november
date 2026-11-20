from django.db.models import Sum

from .models import CartItem


def cart_item_count(request):
    """Expose the total number of units in the signed-in user's cart."""
    if not request.user.is_authenticated:
        return {"cart_item_count": 0}

    total = CartItem.objects.filter(cart__user=request.user).aggregate(
        total=Sum("quantity")
    )["total"]
    return {"cart_item_count": total or 0}
