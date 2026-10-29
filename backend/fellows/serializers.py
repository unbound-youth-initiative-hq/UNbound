import re

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import Task, MeetingAvailability, AvailabilityRequest


class TaskSerializer(serializers.ModelSerializer):
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_change_status = serializers.SerializerMethodField()
    availability_request_id = serializers.PrimaryKeyRelatedField(
        source='availability_request',
        read_only=True
    )

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'scope', 'status', 'source',
            'assigned_to', 'cohort', 'icon', 'color', 'due_date', 'created_at',
            'availability_request_id', 'can_edit', 'can_delete', 'can_change_status',
        ]
        read_only_fields = ['id', 'created_at', 'source', 'assigned_to', 'cohort', 'availability_request_id']

    def get_can_edit(self, obj):
        request = self.context.get('request')
        return bool(request and obj.can_manage(request.user))

    def get_can_delete(self, obj):
        return self.get_can_edit(obj)

    def get_can_change_status(self, obj):
        return not bool(obj.availability_request_id)

    def validate_icon(self, value):
        if value and not re.fullmatch(r'fa-[a-z0-9-]+', value):
            raise serializers.ValidationError('Choose a valid icon name.')
        return value

    def validate_color(self, value):
        if value and not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise serializers.ValidationError('Use a six-digit hex color, such as #00B4D8.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        fellow = getattr(request.user, 'fellow_profile', None) if request else None
        if fellow is None:
            raise PermissionDenied('A fellow profile is required to manage tasks.')

        supplied = set(self.initial_data)
        protected = {'source', 'assigned_to', 'cohort', 'availability_request', 'availability_request_id'}
        if supplied & protected:
            raise PermissionDenied('Assignment recipients and source are managed by staff.')
        if self.instance:
            if 'scope' in supplied:
                raise PermissionDenied('An existing task cannot be moved between personal and team assignments.')
            if self.instance.availability_request_id and 'status' in supplied:
                raise serializers.ValidationError({'status': 'Submit availability in Meeting Hub to update this task.'})
            if not self.instance.can_manage(request.user) and supplied - {'status'}:
                raise PermissionDenied('You can update the status of this assignment, but only its owner or staff can edit it.')
        elif attrs.get('scope') == Task.Scope.TEAM and not fellow.cohort_id:
            raise serializers.ValidationError({'scope': 'Join a cohort before creating a team task.'})
        return attrs


class MeetingAvailabilitySerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        from .availability import request_for_fellow, validate_slot
        fellow = getattr(self.context['request'].user, 'fellow_profile', None)
        instance = self.instance
        meeting = attrs.get('availability_request', instance.availability_request if instance else None)
        if instance and meeting != instance.availability_request:
            raise serializers.ValidationError({'availability_request': 'A saved slot cannot be moved to another request.'})
        meeting = request_for_fellow(fellow, meeting.pk if meeting else None)
        slot = {name: attrs.get(name, getattr(instance, name, None)) for name in ('date', 'hour', 'is_available')}
        attrs.update(validate_slot(meeting, slot))
        return attrs

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
        return obj.submissions.filter(fellow=fellow).exists()

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
