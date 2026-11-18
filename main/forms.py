from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
            field.widget.attrs.setdefault("data-lpignore", "true")
            field.widget.attrs.setdefault("data-1p-ignore", "true")
            field.widget.attrs.setdefault("data-bwignore", "true")

    def clean_language(self):
        return self.cleaned_data.get("language", "").strip().lower()

    class Meta:
        model = Product
        fields = (
            "category",
            "manufacturer",
            "name",
            "sku",
            "description",
            "price",
            "min_age",
            "min_players",
            "max_players",
            "duration_min",
            "language",
            "image",
            "is_active",
        )
        widgets = {
            "category": forms.Select(attrs={"autocomplete": "off"}),
            "manufacturer": forms.Select(attrs={"autocomplete": "off"}),
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "sku": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 4, "autocomplete": "off"}),
            "price": forms.TextInput(attrs={
                "inputmode": "decimal",
                "autocomplete": "off",
                "pattern": r"[0-9]+([.][0-9]{1,2})?",
                "min": "0",
            }),
            "min_age": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "min_players": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "max_players": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "duration_min": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "language": forms.TextInput(attrs={"autocomplete": "off"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Изображение должно быть не больше 5 МБ.")
            content_type = getattr(image, "content_type", None)
            if content_type and content_type not in {
                "image/jpeg",
                "image/png",
                "image/webp",
            }:
                raise forms.ValidationError("Разрешены изображения JPEG, PNG и WebP.")
        return image
