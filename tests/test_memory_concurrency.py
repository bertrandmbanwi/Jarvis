"""MemoryStore must be thread-safe so brain can run memory I/O off the event loop."""
import threading

from jarvis.memory import store as store_mod


def test_add_is_thread_safe(monkeypatch):
    # Isolate from the real SQLite/Chroma backends; exercise the in-memory path.
    monkeypatch.setattr(store_mod.sqlite_store, "remember", lambda **_kwargs: None)
    memory = store_mod.MemoryStore()  # _collection is None -> _fallback_memory path
    assert memory._collection is None

    per_thread = 200
    threads = 4

    def worker():
        for _ in range(per_thread):
            memory.add("hi")

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    # Without the lock, concurrent `self._counter += 1` and list appends would
    # race and lose entries; the lock makes both exact.
    assert memory._counter == threads * per_thread
    assert len(memory._fallback_memory) == threads * per_thread
