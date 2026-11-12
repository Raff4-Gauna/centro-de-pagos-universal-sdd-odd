"""Response shapes of the identity API (design.md §6.2).

Output only: ``/api/me/`` takes no input. ``MembershipSerializer`` mirrors ``MembershipSummary``,
whose final shape SPEC-02 fixes (``T-TEN-12``); identity passes the list along as the selector
returns it.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.identity.ports.memberships import MembershipSummary


class MembershipSerializer(serializers.Serializer[MembershipSummary]):
    organization_id = serializers.UUIDField(read_only=True)
    organization_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        ref_name = "Membership"


# The authenticated person (RN-IDA-18): identity plus active memberships. A comment, not a
# docstring: drf-spectacular would publish a docstring as the component's description.
class MeSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    # Stored as '' when Google sends none or an unusable one; the contract says null.
    avatar_url = serializers.SerializerMethodField()
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        ref_name = "Me"

    def get_avatar_url(self, me: dict[str, Any]) -> str | None:
        avatar_url: str = me["avatar_url"]
        return avatar_url or None
