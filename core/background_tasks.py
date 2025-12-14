"""Background tasks for Google Sheets synchronization."""
import asyncio
import logging
import os
from typing import Optional
from core.sheets_cache import GoogleSheetsCacheService

logger = logging.getLogger(__name__)


async def fallback_polling_task(cache_service: GoogleSheetsCacheService):
    """Fallback polling task - runs periodically as safety net.
    
    This ensures cache is synced even if webhooks fail.
    Runs once per day by default.
    
    Args:
        cache_service: Google Sheets cache service instance
    """
    poll_interval = int(os.getenv("SHEETS_FALLBACK_POLL_INTERVAL", "86400"))  # 24 hours default
    poll_enabled = os.getenv("SHEETS_FALLBACK_POLL_ENABLED", "true").lower() == "true"
    
    if not poll_enabled:
        logger.info("Fallback polling is disabled")
        return
    
    logger.info(f"Starting fallback polling task (interval: {poll_interval}s)")
    
    while True:
        try:
            # Wait for poll interval
            await asyncio.sleep(poll_interval)
            
            logger.info("Running fallback polling (daily safety check)")
            
            # Get all configured sheets
            sheet_names = cache_service.sheet_names
            
            for sheet_name in sheet_names:
                try:
                    updated = cache_service.sync_sheet(sheet_name)
                    if updated:
                        logger.info(f"Fallback sync updated {sheet_name}")
                    else:
                        logger.debug(f"No changes in {sheet_name} (fallback check)")
                except Exception as e:
                    logger.error(f"Error in fallback sync for {sheet_name}: {e}")
                    # Continue with other sheets
        
        except asyncio.CancelledError:
            logger.info("Fallback polling task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in fallback polling task: {e}")
            # Wait 1 hour before retrying on error
            await asyncio.sleep(3600)

