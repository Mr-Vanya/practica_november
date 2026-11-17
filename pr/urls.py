from django.urls import include, path

urlpatterns = [path("", include("main.urls"))]
handler404 = 'main.views.page_not_found'