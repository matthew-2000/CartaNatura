from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('gis', views.gis, name='gis'),
]
