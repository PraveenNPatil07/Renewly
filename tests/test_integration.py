import pytest
import asyncio
from datetime import date
from application.ingestion_service import IngestionService
from application.query_service import QueryService
from application.cleanup_service import CleanupService
from memory.local_adapter import LocalCogneeAdapter
import cognee
from domain.models import ItemStatus

@pytest.fixture
def adapter():
    import os
    # We will use a separate test data dir to avoid corrupting the main one
    os.environ["COGNEE_DATA_DIR"] = ".renewly/cognee_data_test"
    cognee.config.data_root_directory(".renewly/cognee_data_test")
    return LocalCogneeAdapter(".renewly/cognee_data_test")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_lifecycle(adapter):
    # Reset DB
    try:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
    except:
        pass
        
    await adapter._ensure_initialized()
    ingestor = IngestionService(adapter)
    query_svc = QueryService(adapter)
    cleanup_svc = CleanupService(adapter)
    
    # 1. Ingest
    item = await ingestor.remember_item("My fake gym membership is $25, renews 2030-01-01")
    assert item.price == 25.0
    assert item.status == ItemStatus.ACTIVE
    
    # 2. Ask (should retrieve and format it)
    answer = await query_svc.ask("what gym membership do I have?")
    assert "fake gym" in answer.lower() or "25" in answer or "2030" in answer
    
    # 3. Ask irrelevant (should filter it)
    answer2 = await query_svc.ask("how much is my car insurance?")
    assert "don't have anything relevant" in answer2
    
    # 4. Cancel
    text = (
        f"Life admin item — item_id:{item.item_id}\n"
        f"Name: (Cancelled Item)\n"
        f"Category: subscription\n"
        f"Vendor: none\n"
        f"Key Date: 1970-01-01\n"
        f"Status: cancelled\n"
        f"Related Items: none\n"
        f"Notes: \n"
    )
    await cognee.add(text, dataset_name="renewly")
    await cognee.cognify()
    
    # 5. Cleanup
    raw_results = await adapter.list_all_items()
    assert len(raw_results) > 0 # At least the cancelled chunk
    
    from domain.models import LifeAdminItem, Category
    items = []
    for r in raw_results:
        try:
            items.append(LifeAdminItem(
                item_id=r.get("item_id", "unknown"),
                name=r.get("name", ""),
                category=Category(r.get("category", "other")),
                vendor=r.get("vendor", ""),
                key_date=date.fromisoformat(r["key_date"]),
                price=r.get("price"),
                notes=r.get("notes", ""),
                status=ItemStatus(r.get("status", "active")),
                related_item_ids=r.get("related_item_ids", []),
            ))
        except:
            pass
            
    pruned = await cleanup_svc.run_cleanup(items)
    assert item.item_id in pruned
