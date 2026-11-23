import re

from django import forms
from django.contrib.auth.forms import UserCreationForm

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

    def clean_min_players(self):
        value = self.cleaned_data["min_players"]
        if value < 1:
            raise forms.ValidationError("Укажите не меньше одного игрока.")
        return value

    def clean_max_players(self):
        value = self.cleaned_data["max_players"]
        if value < 1:
            raise forms.ValidationError("Укажите не меньше одного игрока.")
        return value

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Файл больше 5 МБ. Выберите изображение меньшего размера.")
            content_type = getattr(image, "content_type", None)
            if content_type and content_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise forms.ValidationError("Формат не поддерживается. Выберите файл JPEG, PNG или WebP.")
        return image

    def clean(self):
        cleaned_data = super().clean()
        minimum = cleaned_data.get("min_players")
        maximum = cleaned_data.get("max_players")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("max_players", "Число игроков «до» меньше значения «от». Увеличьте его или исправьте диапазон.")
        return cleaned_data

    class Meta:
        model = Product
        fields = (
            "category", "manufacturer", "name", "sku", "description", "price",
            "min_age", "min_players", "max_players", "duration_min", "language",
            "image", "is_active",
        )
        help_texts = {
            "name": "Укажите название, которое увидит покупатель.",
            "sku": "Артикул должен быть уникальным для каждого товара.",
            "price": "Введите сумму в рублях, например 1490.00.",
            "min_age": "Укажите минимальный возраст в полных годах.",
            "min_players": "Нижняя граница количества игроков.",
            "max_players": "Верхняя граница; она должна быть не меньше значения «от».",
            "duration_min": "Продолжительность в минутах; поле можно оставить пустым.",
            "language": "Например: русский. Значение сохранится в нижнем регистре.",
            "image": "Формат JPEG, PNG или WebP, размер не более 5 МБ.",
        }
        error_messages = {
            "category": {"required": "Выберите категорию товара."},
            "manufacturer": {"required": "Выберите производителя."},
            "name": {"required": "Введите название товара.", "max_length": "Сократите название до 200 символов."},
            "sku": {"required": "Введите артикул товара.", "unique": "Такой артикул уже занят. Укажите другой.", "max_length": "Артикул должен быть не длиннее 40 символов."},
            "price": {"required": "Укажите цену товара.", "invalid": "Введите цену числом, например 1490.00.", "min_value": "Цена не может быть отрицательной.", "max_digits": "Проверьте цену: допустимо не более 10 цифр всего.", "max_decimal_places": "Оставьте не более двух цифр после запятой."},
            "min_age": {"required": "Укажите минимальный возраст.", "invalid": "Введите возраст целым числом.", "min_value": "Возраст не может быть отрицательным.", "max_value": "Укажите возраст не больше 99 лет."},
            "min_players": {"required": "Укажите минимальное количество игроков.", "invalid": "Введите количество игроков целым числом."},
            "max_players": {"required": "Укажите максимальное количество игроков.", "invalid": "Введите количество игроков целым числом."},
            "duration_min": {"invalid": "Введите длительность целым числом минут."},
        }
        widgets = {
            "category": forms.Select(attrs={"autocomplete": "off"}),
            "manufacturer": forms.Select(attrs={"autocomplete": "off"}),
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "sku": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 4, "autocomplete": "off"}),
            "price": forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off", "pattern": r"[0-9]+([.][0-9]{1,2})?", "min": "0"}),
            "min_age": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "min_players": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "max_players": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "duration_min": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "pattern": "[0-9]*"}),
            "language": forms.TextInput(attrs={"autocomplete": "off"}),
        }


class CheckoutForm(forms.Form):
    contact_name = forms.CharField(label="Имя и фамилия", max_length=150, strip=True, help_text="Укажите имя получателя заказа.", error_messages={"required": "Введите имя получателя.", "max_length": "Сократите имя до 150 символов."}, widget=forms.TextInput(attrs={"class": "field", "autocomplete": "name"}))
    phone = forms.CharField(label="Телефон", max_length=30, strip=True, help_text="Введите 10–15 цифр; можно использовать +, пробелы, дефисы и скобки.", error_messages={"required": "Введите номер телефона.", "max_length": "Проверьте длину номера телефона."}, widget=forms.TextInput(attrs={"class": "field", "type": "tel", "autocomplete": "tel"}))
    email = forms.EmailField(label="Электронная почта", max_length=254, help_text="Укажите адрес в формате name@example.com.", error_messages={"required": "Введите электронную почту.", "invalid": "Проверьте адрес: нужен формат name@example.com."}, widget=forms.EmailInput(attrs={"class": "field", "autocomplete": "email"}))
    pickup_point = forms.CharField(label="Пункт выдачи", max_length=200, strip=True, help_text="Укажите адрес или название пункта выдачи.", error_messages={"required": "Укажите пункт выдачи.", "max_length": "Сократите адрес до 200 символов."}, widget=forms.TextInput(attrs={"class": "field", "autocomplete": "off"}))

    def clean_contact_name(self):
        value = " ".join(self.cleaned_data["contact_name"].split())
        if len(value) < 2:
            raise forms.ValidationError("Введите имя получателя полностью (не менее 2 символов).")
        return value

    def clean_phone(self):
        value = self.cleaned_data["phone"]
        if not re.fullmatch(r"[0-9+()\-\s]+", value):
            raise forms.ValidationError("Оставьте в телефоне только цифры и символы +, (), дефис или пробел.")
        if not 10 <= len(re.sub(r"\D", "", value)) <= 15:
            raise forms.ValidationError("Номер должен содержать от 10 до 15 цифр. Проверьте код страны и номер.")
        return value


class LoginForm(forms.Form):
    username = forms.CharField(label="Имя пользователя", strip=True, error_messages={"required": "Введите имя пользователя."}, widget=forms.TextInput(attrs={"class": "field", "autocomplete": "username"}))
    password = forms.CharField(label="Пароль", strip=False, error_messages={"required": "Введите пароль."}, widget=forms.PasswordInput(attrs={"class": "field", "autocomplete": "current-password"}))


class RussianUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "До 150 символов: буквы, цифры и символы @/./+/-/_."
        self.fields["password1"].help_text = "Используйте пароль, который сложно угадать."
        self.fields["password2"].help_text = "Повторите пароль без изменений."
        self.fields["username"].error_messages.update({"required": "Введите имя пользователя.", "invalid": "Используйте допустимые символы в имени пользователя.", "unique": "Это имя уже занято. Выберите другое."})
        self.fields["password1"].error_messages["required"] = "Придумайте пароль."
        self.fields["password2"].error_messages["required"] = "Повторите пароль."
