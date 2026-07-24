from rest_framework import serializers
from .models import Task, MeetingAvailability

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'scope', 'status', 'source',
            'assigned_to', 'cohort', 'icon', 'color', 'due_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'source', 'assigned_to']

class MeetingAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingAvailability
        fields = ['id', 'fellow', 'day_of_week', 'hour', 'is_available']
        read_only_fields = ['id', 'fellow']
