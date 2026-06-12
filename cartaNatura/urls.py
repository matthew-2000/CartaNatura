from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('gis', views.gis, name='gis'),
    path('interact', views.interact, name='interact'),
    path('interact/stream', views.interact_stream, name='interact_stream'),
]
