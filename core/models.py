from django.db import models
from django.contrib.auth.models import User

# FR-37: Configure departments
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

# FR-12 & FR-37: Configure stations and geofencing
class Station(models.Model):
    name = models.CharField(max_length=100, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="e.g., -0.4197")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="e.g., 36.9522")
    geofence_radius_meters = models.IntegerField(default=100, help_text="Allowed distance from station in meters")

    def __str__(self):
        return self.name

# FR-5: Maintain employee profiles
class Employee(models.Model):
    CONTRACT_CHOICES = [
        ('PERMANENT', 'Permanent'),
        ('CONTRACT', 'Contract'),
        ('INTERN', 'Intern'),
    ]
    
    # Links to Django's built-in User model for secure login (FR-1, FR-4)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    
    staff_number = models.CharField(max_length=20, unique=True)
    national_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='employees')
    station = models.ForeignKey(Station, on_delete=models.SET_NULL, null=True, related_name='employees')
    job_title = models.CharField(max_length=100)
    contract_type = models.CharField(max_length=20, choices=CONTRACT_CHOICES)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True) # FR-7: Activate, suspend or deactivate

    def __str__(self):
        return f"{self.staff_number} - {self.first_name} {self.last_name}"

# FR-8, FR-9, FR-10, FR-11, FR-12: Clock-in/out records
class AttendanceRecord(models.Model):
    METHOD_CHOICES = [
        ('WEB', 'Web/Mobile App'),
        ('BIOMETRIC', 'Biometric Terminal'),
        ('QR', 'QR Code / Card'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(auto_now_add=True) # FR-10: Server date
    clock_in_time = models.DateTimeField(null=True, blank=True) # FR-10: Server time
    clock_out_time = models.DateTimeField(null=True, blank=True)
    
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='WEB')
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True) # FR-9, FR-12
    location_lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True) # FR-9, FR-12
    is_within_geofence = models.BooleanField(default=False, help_text="Auto-calculated on clock-in") # FR-12
    
    notes = models.TextField(blank=True, null=True, help_text="e.g., Field assignment reason") # FR-12

    class Meta:
        # FR-11: Prevents duplicate clock-ins for the same employee on the same day
        constraints = [
            models.UniqueConstraint(fields=['employee', 'date'], name='unique_daily_clock_in')
        ]

    def __str__(self):
        return f"{self.employee.staff_number} on {self.date}"