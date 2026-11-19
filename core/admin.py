from django.contrib import admin
from .models import Department, Station, Employee, AttendanceRecord

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude', 'geofence_radius_meters')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('staff_number', 'first_name', 'last_name', 'department', 'station', 'is_active')
    list_filter = ('department', 'station', 'is_active')
    search_fields = ('staff_number', 'first_name', 'last_name', 'national_id')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'clock_in_time', 'clock_out_time', 'method', 'is_within_geofence')
    list_filter = ('date', 'method', 'is_within_geofence')
    search_fields = ('employee__staff_number', 'employee__first_name')