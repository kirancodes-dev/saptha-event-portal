from flask_mail import Message
from flask import current_app

def send_credentials_email(to_email, name, role, password, category="General"):
    """Sends new users their auto-generated login password."""
    try:
        mail = current_app.extensions.get('mail')
        msg = Message(f"Welcome to SapthaEvent - Your {role} Login", recipients=[to_email])
        msg.body = f"Hello {name},\n\nYou have been registered as a {role} for the {category} division on the SapthaEvent Portal.\n\nHere are your login credentials:\nEmail: {to_email}\nPassword: {password}\n\nPlease login at the portal to access your dashboard.\n\nBest Regards,\nSapthaEvent Admin"
        mail.send(msg)
        return True
    except Exception as e:
        print("Email Error:", e)
        return False

def send_appointment_email(to_email, name, role, event_title):
    """Sends existing users a notification that they were promoted to Judge/Coordinator."""
    try:
        mail = current_app.extensions.get('mail')
        msg = Message(f"Event Appointment: {role} for {event_title}", recipients=[to_email])
        msg.body = f"Hello {name},\n\nYou have been officially appointed as a {role} for the upcoming event: '{event_title}'.\n\nYour account privileges have been updated. Please log in using your existing student/staff email and password to access your new {role} dashboard.\n\nBest Regards,\nSapthaEvent Coordinators"
        mail.send(msg)
        return True
    except Exception as e:
        print("Email Error:", e)
        return False

def send_broadcast_email(email_list, subject, message, event_title):
    """Sends a mass message to all participants."""
    try:
        mail = current_app.extensions.get('mail')
        with mail.connect() as conn:
            for email in email_list:
                msg = Message(f"[{event_title} Update] {subject}", recipients=[email])
                msg.body = f"Important update regarding {event_title}:\n\n{message}\n\nRegards,\nEvent Organizers"
                conn.send(msg)
        return True
    except Exception as e:
        print("Broadcast Email Error:", e)
        return False
        
def send_ticket_email(email, name, event_title, reg_id):
    """Sends the registration ticket."""
    try:
        mail = current_app.extensions.get('mail')
        msg = Message(f"Ticket Confirmed: {event_title}", recipients=[email])
        msg.body = f"Hello {name},\n\nYour registration for {event_title} is confirmed!\n\nYour Ticket ID is: {reg_id}\n\nPlease show this ID or your registered Email at the venue.\n\nBest Regards,\nSapthaEvent"
        mail.send(msg)
        return True
    except Exception as e:
        print("Ticket Email Error:", e)
        return False