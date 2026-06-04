from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('progettoGIS/cartaNatura/', include('cartaNatura.urls')),
    path('progettoGIS/admin/', admin.site.urls),
]
