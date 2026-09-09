"""Prototype per-process backpressure for expensive local model/media operations."""
from threading import BoundedSemaphore, Lock
from fastapi import Depends, HTTPException
from app.security import current_user

_global = BoundedSemaphore(2)
_guard = Lock()
_active = set()

def processing_slot(user=Depends(current_user)):
    uid = user['id']
    with _guard:
        if uid in _active:
            raise HTTPException(429, 'Your previous generation or revision is still running')
        if not _global.acquire(blocking=False):
            raise HTTPException(429, 'Local processing is busy. Try again shortly.')
        _active.add(uid)
    try:
        yield
    finally:
        with _guard:
            _active.discard(uid)
            _global.release()
