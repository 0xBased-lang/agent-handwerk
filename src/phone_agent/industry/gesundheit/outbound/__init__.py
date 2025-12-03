"""Outbound calling system for Healthcare.

Components:
- OutboundDialer: Manages call queue with priority ordering
- OutboundConversationManager: Handles outbound call conversations
- Workflows: AppointmentReminder, RecallCampaign, NoShowFollowup
"""
from phone_agent.industry.gesundheit.outbound.dialer import (
    OutboundDialer,
    DialerStatus,
    DialerConfig,
    CallPriority,
    QueuedCall,
    get_outbound_dialer,
)
from phone_agent.industry.gesundheit.outbound.conversation_outbound import (
    OutboundConversationManager,
    OutboundState,
    OutboundOutcome,
    OutboundCallType,
    OutboundContext,
)
from phone_agent.industry.gesundheit.outbound.reminder_workflow import (
    AppointmentReminderWorkflow,
    ReminderTask,
    ReminderStatus,
    ReminderCampaignConfig,
    ReminderCampaignStats,
    create_reminder_workflow,
)
from phone_agent.industry.gesundheit.outbound.recall_workflow import (
    RecallCampaignWorkflow,
    RecallCallTask,
    RecallCallStatus,
    RecallCampaignStats,
    create_recall_workflow,
)
from phone_agent.industry.gesundheit.outbound.noshow_workflow import (
    NoShowFollowupWorkflow,
    NoShowFollowupTask,
    NoShowReason,
    NoShowOutcome,
    NoShowConfig,
    NoShowStats,
    create_noshow_workflow,
)

__all__ = [
    # Dialer
    "OutboundDialer",
    "DialerStatus",
    "DialerConfig",
    "CallPriority",
    "QueuedCall",
    "get_outbound_dialer",
    # Conversation
    "OutboundConversationManager",
    "OutboundState",
    "OutboundOutcome",
    "OutboundCallType",
    "OutboundContext",
    # Reminder Workflow
    "AppointmentReminderWorkflow",
    "ReminderTask",
    "ReminderStatus",
    "ReminderCampaignConfig",
    "ReminderCampaignStats",
    "create_reminder_workflow",
    # Recall Workflow
    "RecallCampaignWorkflow",
    "RecallCallTask",
    "RecallCallStatus",
    "RecallCampaignStats",
    "create_recall_workflow",
    # No-Show Workflow
    "NoShowFollowupWorkflow",
    "NoShowFollowupTask",
    "NoShowReason",
    "NoShowOutcome",
    "NoShowConfig",
    "NoShowStats",
    "create_noshow_workflow",
]
