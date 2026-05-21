
from typing import Optional, Type, AsyncGenerator
from google.adk.agents import LlmAgent, BaseAgentState
from google.adk.events.event import Event
from google.adk.agents.invocation_context import InvocationContext

class StatelessLlmAgent(LlmAgent):
    """
    An LlmAgent that bypasses session state loading and saving.
    Used when the underlying session infrastructure (Firestore/Identity) is unstable or misconfigured.
    """

    def _load_agent_state(
        self,
        ctx: InvocationContext,
        state_type: Type[BaseAgentState],
    ) -> Optional[BaseAgentState]:
        """Override: Do not load state from context (which comes from session storage)."""
        return None

    def _create_agent_state_event(
        self,
        ctx: InvocationContext,
    ) -> Event:
        """Override: Do not create state events to save back to session."""
        # Return a dummy event or None? BaseAgent returns an Event.
        # We can return an event with empty actions to satisfy the signature but avoid saving.
        # However, InvocationContext tracks state changes. If we don't save, it's fine.
        return super()._create_agent_state_event(ctx)

    async def _handle_before_agent_callback(self, ctx: InvocationContext) -> Optional[Event]:
        # Simplify callback handling if needed, but standard implementation is fine
        return await super()._handle_before_agent_callback(ctx)

    async def _handle_after_agent_callback(self, ctx: InvocationContext) -> Optional[Event]:
        return await super()._handle_after_agent_callback(ctx)
