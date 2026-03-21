"""
Background Scheduler for RingAI

Handles scheduled tasks:
- Appointment reminders (24 hours before)
- Daily analytics updates
- Cleanup of old data

Uses APScheduler for reliable background task execution.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_running = False


async def process_reminders_task(db):
    """
    Process appointment reminders.
    Called by the scheduler every hour.
    """
    try:
        from reminder_service import process_appointment_reminders
        from websocket_notifications import notify_appointment_reminder
        
        logger.info("Running scheduled reminder task...")
        result = await process_appointment_reminders(db)
        
        # Send WebSocket notifications for sent reminders
        for apt in result.get("appointments", []):
            if apt.get("success"):
                # Get appointment details for notification
                appointment = await db.appointments.find_one(
                    {"id": apt.get("id")},
                    {"_id": 0}
                )
                if appointment:
                    await notify_appointment_reminder(
                        restaurant_id=appointment.get("restaurant_id"),
                        appointment_id=appointment.get("id"),
                        customer_name=appointment.get("customer_name", "Customer"),
                        service_name=appointment.get("service_name", "Appointment"),
                    )
        
        logger.info(
            f"Reminder task complete: {result.get('sent', 0)}/{result.get('processed', 0)} sent"
        )
        return result
        
    except Exception as e:
        logger.error(f"Reminder task error: {e}")
        return {"error": str(e)}


async def cleanup_old_notifications_task(db, days_old: int = 30):
    """
    Clean up old notification records.
    Called daily.
    """
    try:
        cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Keep it simple for now
        # This would delete notifications older than `days_old` days
        # For now, just log
        logger.info(f"Cleanup task: Would clean notifications older than {days_old} days")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Cleanup task error: {e}")
        return {"error": str(e)}


async def scheduler_loop(db, reminder_interval_hours: int = 1):
    """
    Main scheduler loop.
    Runs tasks at specified intervals.
    """
    global _scheduler_running
    _scheduler_running = True
    
    logger.info(f"Scheduler started (reminder interval: {reminder_interval_hours}h)")
    
    last_reminder_run = None
    last_cleanup_run = None
    
    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            
            # Run reminders every hour
            if last_reminder_run is None or (now - last_reminder_run).total_seconds() >= reminder_interval_hours * 3600:
                await process_reminders_task(db)
                last_reminder_run = now
            
            # Run cleanup once a day (at midnight UTC roughly)
            if last_cleanup_run is None or (now - last_cleanup_run).total_seconds() >= 86400:
                await cleanup_old_notifications_task(db)
                last_cleanup_run = now
            
            # Sleep for 5 minutes between checks
            await asyncio.sleep(300)
            
        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled")
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying
    
    _scheduler_running = False
    logger.info("Scheduler stopped")


def start_scheduler(db):
    """Start the background scheduler."""
    global _scheduler_task
    
    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("Scheduler already running")
        return
    
    _scheduler_task = asyncio.create_task(scheduler_loop(db))
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler_task, _scheduler_running
    
    _scheduler_running = False
    
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("Background scheduler stopped")


def is_scheduler_running() -> bool:
    """Check if scheduler is running."""
    return _scheduler_running
