"""URL patterns for the pipeline app."""

from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path("",                    views.dashboard,      name="dashboard"),
    path("sessions/new/",       views.session_new,    name="session_new"),
    path("sessions/<int:pk>/",  views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/edit/", views.session_edit, name="session_edit"),
    path("diagnostics/",        views.diagnostics,    name="diagnostics"),

    # AJAX / API
    path("sessions/<int:pk>/start/",   views.session_start,  name="session_start"),
    path("sessions/<int:pk>/stop/",    views.session_stop,   name="session_stop"),
    path("sessions/<int:pk>/status/",  views.session_status, name="session_status"),
    path("sessions/<int:pk>/rc/",      views.preview_rc,     name="preview_rc"),
    path("diagnostics/run/",           views.run_diagnostics, name="run_diagnostics"),
]
