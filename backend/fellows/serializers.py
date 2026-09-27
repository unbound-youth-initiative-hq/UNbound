from rest_framework import serializers
from .models import Task, MeetingAvailability, AvailabilityRequest


class TaskSerializer(serializers.ModelSerializer):
    availability_request_id = serializers.PrimaryKeyRelatedField(
        source='availability_request',
        read_only=True
    )

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'scope', 'status', 'source',
            'assigned_to', 'cohort', 'icon', 'color', 'due_date', 'created_at',
            'availability_request_id'
        ]
        read_only_fields = ['id', 'created_at', 'source', 'assigned_to', 'availability_request_id']


class MeetingAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingAvailability
        fields = [
            'id', 'availability_request', 'fellow', 'date', 'day_of_week', 'hour', 'is_available'
        ]
        read_only_fields = ['id', 'fellow']


class AvailabilityRequestSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    task_id = serializers.SerializerMethodField()
    total_slots_count = serializers.SerializerMethodField()
    filled_slots_count = serializers.SerializerMethodField()

    class Meta:
        model = AvailabilityRequest
        fields = [
            'id', 'title', 'description', 'start_date', 'end_date',
            'start_hour', 'end_hour', 'cohort', 'assign_to_all',
            'deadline', 'is_active', 'created_at', 'is_completed',
            'task_id', 'total_slots_count', 'filled_slots_count'
        ]

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'fellow_profile'):
            return False
        fellow = request.user.fellow_profile
        # Completed if task is marked complete or user has marked available slots for this request
        task = Task.objects.filter(assigned_to=fellow, availability_request=obj).first()
        if task and task.status == Task.Status.COMPLETE:
            return True
        return MeetingAvailability.objects.filter(
            availability_request=obj,
            fellow=fellow,
            is_available=True
        ).exists()

    def get_task_id(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'fellow_profile'):
            return None
        fellow = request.user.fellow_profile
        task = Task.objects.filter(assigned_to=fellow, availability_request=obj).first()
        return task.id if task else None

    def get_total_slots_count(self, obj):
        days = (obj.end_date - obj.start_date).days + 1
        hours = max(1, obj.end_hour - obj.start_hour)
        return days * hours

    def get_filled_slots_count(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'fellow_profile'):
            return 0
        fellow = request.user.fellow_profile
        return MeetingAvailability.objects.filter(
            availability_request=obj,
            fellow=fellow,
            is_available=True
        ).count()
