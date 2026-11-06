"""
tests/test_task_app_context.py — UPG-110: a background task runs in the Flask
app that was bound most recently, even if the task's class was created before.
Task modules are imported once, so a task defined against an earlier app (a
reloaded app in the tests) must not keep signing with that app's settings.
"""
import threading

from flask import Flask, current_app

import celery_app


def test_a_task_runs_in_the_app_bound_most_recently():
    original = getattr(celery_app, '_flask_app', None)
    first, second = Flask('first'), Flask('second')
    first.config['MARK'], second.config['MARK'] = 'first', 'second'
    try:
        celery_app.init_celery(first)

        @celery_app.celery.task(name='tests.which_app')
        def which_app():
            return current_app.config['MARK']

        assert which_app.name == 'tests.which_app'  # touching it builds the task class, as real use does
        celery_app.init_celery(second)            # the app is rebound after the task exists
        seen = []
        t = threading.Thread(target=lambda: seen.append(which_app.apply().get()))   # no outer app context
        t.start()
        t.join(timeout=10)
        assert seen == ['second']
    finally:
        if original is not None:
            celery_app.init_celery(original)
