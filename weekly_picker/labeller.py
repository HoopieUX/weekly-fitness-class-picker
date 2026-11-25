import asyncio

from weekly_picker.jev import add_physio, class_state, label_questions, physio_questions, to_labels
from weekly_picker.models import AloClass, Labels
from weekly_picker.store import Store


async def label_all_async(
    classes: list[AloClass],
    store: Store,
    client,
    *,
    limit: int | None = None,
    concurrency: int = 8,
    batch_size: int = 50,
) -> int:
    """Label every class not yet labelled. Classes labelled before the physio questions existed get only those
    questions, so their earlier answers stay as they were. Saves after each batch, so an interrupted run loses
    at most one batch."""
    done = store.load_labels()
    todo = [c for c in classes if c.id not in done or not done[c.id].physio]
    if limit is not None:
        todo = todo[:limit]
    gate = asyncio.Semaphore(concurrency)
    failure: list[BaseException] = []

    async def one(c: AloClass) -> Labels | None:
        async with gate:
            if failure:
                return None
            old = done.get(c.id)
            try:
                response = await client.system_one(class_state(c), physio_questions() if old else label_questions(c))
            except Exception as e:  # noqa: BLE001  (re-raised after the batch is saved)
                failure.append(e)
                return None
            return add_physio(old, response) if old else to_labels(c, response)

    labelled = 0
    for start in range(0, len(todo), batch_size):
        results = await asyncio.gather(*(one(c) for c in todo[start:start + batch_size]))
        batch = [l for l in results if l is not None]
        if batch:
            store.save_labels(batch)
            labelled += len(batch)
        if failure:
            raise failure[0]
    return labelled


def label_all(classes, store, client, **kw) -> int:
    return asyncio.run(label_all_async(classes, store, client, **kw))
