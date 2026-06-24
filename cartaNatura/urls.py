from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('gis', views.gis, name='gis'),
    path('analysis/history', views.analysis_history, name='analysis_history'),
    path('analysis/history/compare', views.analysis_history_compare, name='analysis_history_compare'),
    path('analysis/history/<str:analysis_id>', views.analysis_history_detail, name='analysis_history_detail'),
    path('interact', views.interact, name='interact'),
    path('interact/stream', views.interact_stream, name='interact_stream'),
    path('voice/transcribe', views.voice_transcribe, name='voice_transcribe'),
    path('experiment/log', views.experiment_log, name='experiment_log'),
    path('experiment/study/session', views.study_session, name='study_session'),
]
