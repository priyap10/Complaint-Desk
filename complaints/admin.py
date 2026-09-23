from django.contrib import admin

from .models import Attachment, Category, Comment, Complaint, StatusHistory


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ('author', 'message', 'is_internal', 'created_at')
    readonly_fields = ('created_at',)
    raw_id_fields = ('author',)


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ('file', 'uploaded_by', 'uploaded_at')
    readonly_fields = ('uploaded_at',)
    raw_id_fields = ('uploaded_by',)


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    can_delete = False
    fields = ('changed_at', 'old_status', 'new_status', 'changed_by', 'note')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'complaint_count')
    list_filter = ('is_active',)
    search_fields = ('name',)

    @admin.display(description='Complaints')
    def complaint_count(self, obj):
        return obj.complaints.count()


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        'ticket_id', 'title', 'category', 'priority', 'status',
        'complainant', 'assigned_to', 'created_at',
    )
    list_filter = ('status', 'priority', 'category', 'created_at')
    search_fields = ('ticket_id', 'title', 'description', 'complainant__username', 'complainant__email')
    readonly_fields = ('ticket_id', 'created_at', 'updated_at', 'resolved_at')
    raw_id_fields = ('complainant', 'assigned_to')
    list_select_related = ('category', 'complainant', 'assigned_to')
    date_hierarchy = 'created_at'
    inlines = [StatusHistoryInline, CommentInline, AttachmentInline]

    def save_model(self, request, obj, form, change):
        obj._changed_by = request.user  # so the history shows who used the admin site
        super().save_model(request, obj, form, change)