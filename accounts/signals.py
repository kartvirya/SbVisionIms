from django.db.models.signals import post_save
from django.dispatch import receiver

from django.contrib.auth.models import User
from .models import Profile


@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Signal handler to create or update a Profile when a User is saved.
    """
    if created:
        Profile.objects.create(
            user=instance,
            email=instance.email or None,
        )
        print('Profile created!')
    else:
        try:
            profile = instance.profile
        except Profile.DoesNotExist:
            Profile.objects.create(
                user=instance,
                email=instance.email or None,
            )
            print('Profile created!')
            return
        if instance.email and profile.email != instance.email:
            profile.email = instance.email
        profile.save()
        print('Profile updated!')
