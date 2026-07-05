import boto3
import hmac
import hashlib
import base64
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Attr
import os
from werkzeug.utils import secure_filename

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Cognito Client
client = boto3.client(
    "cognito-idp",
    region_name=Config.AWS_REGION
)
# DynamoDB
dynamodb = boto3.resource(
    "dynamodb",
    region_name=Config.AWS_REGION
)
# S3 Client
s3 = boto3.client(
    "s3",
    region_name=Config.AWS_REGION
)

events_table = dynamodb.Table("CloudRSVPEvents")
rsvp_table = dynamodb.Table("CloudRSVPs")
invite_table = dynamodb.Table("CloudInvitations")
photos_table = dynamodb.Table("CloudEventPhotos")

# --------------------------------------------------
# Generate Cognito Secret Hash
# --------------------------------------------------

def get_secret_hash(username):
    message = username + Config.COGNITO_CLIENT_ID

    digest = hmac.new(
        Config.COGNITO_CLIENT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()

    return base64.b64encode(digest).decode()


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", title="Home")


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        try:

            response = client.initiate_auth(
                ClientId=Config.COGNITO_CLIENT_ID,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email,
                    "PASSWORD": password,
                    "SECRET_HASH": get_secret_hash(email)
                }
            )

            session["user"] = email
            session["token"] = response["AuthenticationResult"]["AccessToken"]

            flash("Login Successful!", "success")

            return redirect(url_for("dashboard"))

        except client.exceptions.UserNotConfirmedException:
            flash("Please confirm your account first.", "danger")

        except client.exceptions.NotAuthorizedException:
            flash("Invalid email or password.", "danger")

        except Exception as e:
            print(e)
            flash(str(e), "danger")

    return render_template("login.html", title="Login")


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", title="Register")

        try:

            client.sign_up(
                ClientId=Config.COGNITO_CLIENT_ID,
                SecretHash=get_secret_hash(email),
                Username=email,
                Password=password,
                UserAttributes=[
                    {
                        "Name": "email",
                        "Value": email
                    },
                    {
                        "Name": "given_name",
                        "Value": first_name
                    },
                    {
                        "Name": "family_name",
                        "Value": last_name
                    }
                ]
            )

            flash(
                "Registration successful! Please verify your email or confirm the user in Cognito.",
                "success"
            )

            return redirect(url_for("login"))

        except client.exceptions.UsernameExistsException:
            flash("User already exists.", "danger")

        except Exception as e:
            print(e)
            flash(str(e), "danger")

    return render_template("register.html", title="Register")


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        title="Dashboard",
        user=session["user"]
    )

# --------------------------------------------------
# CREATE EVENT
# --------------------------------------------------

@app.route("/create-event", methods=["GET", "POST"])
def create_event():

    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        banner_url = ""

        # Upload banner to S3 (optional)
        banner = request.files.get("banner")

        if banner and banner.filename != "":

            filename = secure_filename(banner.filename)

            s3_key = f"event-banners/{uuid.uuid4()}_{filename}"

            s3.upload_fileobj(
                banner,
                Config.S3_BUCKET_NAME,
                s3_key
            )

            banner_url = (
                f"https://{Config.S3_BUCKET_NAME}.s3."
                f"{Config.AWS_REGION}.amazonaws.com/{s3_key}"
            )

        # Save event to DynamoDB
        event = {
            "event_id": str(uuid.uuid4()),
            "event_name": request.form["event_name"],
            "venue": request.form["venue"],
            "description": request.form["description"],
            "date": request.form["date"],
            "time": request.form["time"],
            "max_participants": request.form["max_participants"],
            "banner_url": banner_url,
            "created_by": session["user"]
        }

        events_table.put_item(Item=event)

        flash("Event created successfully!", "success")

        return redirect(url_for("events"))

    return render_template(
        "create_event.html",
        title="Create Event"
    )
# --------------------------------------------------
# EVENTS
# --------------------------------------------------
@app.route("/events")
def events():

    response = events_table.scan()

    all_events = response.get("Items", [])

    return render_template(
        "events.html",
        title="Events",
        events=all_events
    )

@app.route("/events/<int:event_id>")
def event_details(event_id):

    return render_template(
        "event_details.html",
        title="Event Details",
        event_id=event_id
    )
# --------------------------------------------------
# RSVP
# --------------------------------------------------

@app.route("/rsvp/<event_id>")
def rsvp(event_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = events_table.get_item(
        Key={
            "event_id": event_id
        }
    )

    if "Item" not in response:
        flash("Event not found.", "danger")
        return redirect(url_for("events"))

    event = response["Item"]

    # Prevent duplicate RSVP
    existing = rsvp_table.scan()

    for item in existing.get("Items", []):

        if (
            item["event_id"] == event_id
            and item["user_email"] == session["user"]
        ):
            flash("You have already RSVP'd for this event.", "warning")
            return redirect(url_for("events"))

    # Save RSVP
    rsvp_table.put_item(
        Item={
            "rsvp_id": str(uuid.uuid4()),
            "event_id": event_id,
            "event_name": event["event_name"],
            "user_email": session["user"],
            "organizer_email": event["created_by"],
            "status": "Pending",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

    flash("RSVP submitted successfully!", "success")

    return redirect(url_for("my_rsvps"))
# --------------------------------------------------
# MY RSVPS
# --------------------------------------------------
@app.route("/my-rsvps")
def my_rsvps():

    if "user" not in session:
        return redirect(url_for("login"))

    response = rsvp_table.scan()

    my_list = []

    for item in response.get("Items", []):

        if (
            item["user_email"] == session["user"]
            or item["organizer_email"] == session["user"]
        ):
            my_list.append(item)

    return render_template(
        "my_rsvps.html",
        title="My RSVPs",
        rsvps=my_list,
        current_user=session["user"]
    )
# --------------------------------------------------
# ACCEPT RSVP
# --------------------------------------------------
@app.route("/accept/<rsvp_id>")
def accept_rsvp(rsvp_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = rsvp_table.get_item(Key={"rsvp_id": rsvp_id})

    if "Item" not in response:
        flash("RSVP not found.", "danger")
        return redirect(url_for("my_rsvps"))

    item = response["Item"]

    if item["organizer_email"] != session["user"]:
        flash("Only the organizer can accept RSVPs.", "danger")
        return redirect(url_for("my_rsvps"))

    item["status"] = "Accepted"

    rsvp_table.put_item(Item=item)

    flash("RSVP Accepted.", "success")

    return redirect(url_for("my_rsvps"))
# --------------------------------------------------
# REJECT RSVP
# --------------------------------------------------
@app.route("/reject/<rsvp_id>")
def reject_rsvp(rsvp_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = rsvp_table.get_item(Key={"rsvp_id": rsvp_id})

    if "Item" not in response:
        flash("RSVP not found.", "danger")
        return redirect(url_for("my_rsvps"))

    item = response["Item"]

    if item["organizer_email"] != session["user"]:
        flash("Only the organizer can reject RSVPs.", "danger")
        return redirect(url_for("my_rsvps"))

    item["status"] = "Rejected"

    rsvp_table.put_item(Item=item)

    flash("RSVP Rejected.", "warning")

    return redirect(url_for("my_rsvps"))

# --------------------------------------------------
# SEND INVITATION
# --------------------------------------------------

@app.route("/send-invite/<event_id>", methods=["POST"])
def send_invite(event_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = events_table.get_item(
        Key={
            "event_id": event_id
        }
    )

    if "Item" not in response:
        flash("Event not found.", "danger")
        return redirect(url_for("events"))

    event = response["Item"]

    invitee_email = request.form["invitee_email"]

    invite_table.put_item(
        Item={
            "invite_id": str(uuid.uuid4()),
            "event_id": event_id,
            "event_name": event["event_name"],
            "organizer_email": session["user"],
            "invitee_email": invitee_email,
            "status": "Pending",
            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

    flash("Invitation sent successfully!", "success")

    return redirect(url_for("events"))

# --------------------------------------------------
# MY INVITATIONS
# --------------------------------------------------

@app.route("/my-invitations")
def my_invitations():

    if "user" not in session:
        return redirect(url_for("login"))

    response = invite_table.scan()

    invitations = []

    for item in response.get("Items", []):

        if item["invitee_email"] == session["user"]:
            invitations.append(item)

    return render_template(
        "my_invitations.html",
        title="My Invitations",
        invitations=invitations
    )

# --------------------------------------------------
# ACCEPT INVITATION
# --------------------------------------------------

@app.route("/accept-invitation/<invite_id>")
def accept_invitation(invite_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = invite_table.get_item(
        Key={
            "invite_id": invite_id
        }
    )

    if "Item" not in response:
        flash("Invitation not found.", "danger")
        return redirect(url_for("my_invitations"))

    invite = response["Item"]

    rsvp_table.put_item(
        Item={
            "rsvp_id": str(uuid.uuid4()),
            "event_id": invite["event_id"],
            "event_name": invite["event_name"],
            "user_email": session["user"],
            "organizer_email": invite["organizer_email"],
            "status": "Pending",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    )

    invite["status"] = "Accepted"

    invite_table.put_item(Item=invite)

    flash("Invitation accepted successfully!", "success")

    return redirect(url_for("my_rsvps"))

# --------------------------------------------------
# REJECT INVITATION
# --------------------------------------------------

@app.route("/reject-invitation/<invite_id>")
def reject_invitation(invite_id):

    if "user" not in session:
        return redirect(url_for("login"))

    response = invite_table.get_item(
        Key={
            "invite_id": invite_id
        }
    )

    if "Item" not in response:
        flash("Invitation not found.", "danger")
        return redirect(url_for("my_invitations"))

    invite = response["Item"]

    invite["status"] = "Rejected"

    invite_table.put_item(Item=invite)

    flash("Invitation rejected.", "warning")

    return redirect(url_for("my_invitations"))

# --------------------------------------------------
# UPLOAD
# --------------------------------------------------

@app.route("/upload")
def upload():

    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "upload.html",
        title="Upload Photos"
    )

# --------------------------------------------------
# UPLOAD EVENT PHOTO
# --------------------------------------------------

@app.route("/upload-event-photo", methods=["GET", "POST"])
def upload_event_photo():

    if "user" not in session:
        return redirect(url_for("login"))

    events = events_table.scan().get("Items", [])

    if request.method == "POST":

        event_id = request.form["event_id"]

        # -----------------------------
        # Get Event Details
        # -----------------------------
        response = events_table.get_item(
            Key={"event_id": event_id}
        )

        if "Item" not in response:
            flash("Event not found.", "danger")
            return redirect(url_for("upload_event_photo"))

        event = response["Item"]

        # -----------------------------
        # Check Event Date & Time
        # -----------------------------
        try:
            event_datetime = datetime.strptime(
                f"{event['date']} {event['time']}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            flash("Invalid event date or time.", "danger")
            return redirect(url_for("upload_event_photo"))

        if datetime.now() < event_datetime:
            flash(
                "Photo uploads are allowed only after the event has ended.",
                "warning"
            )
            return redirect(url_for("upload_event_photo"))

        # -----------------------------
        # Check Accepted RSVP
        # -----------------------------
        response = rsvp_table.scan()

        allowed = False

        for rsvp in response.get("Items", []):

            if (
                rsvp["event_id"] == event_id
                and rsvp["user_email"] == session["user"]
                and rsvp["status"] == "Accepted"
            ):
                allowed = True
                break

        if not allowed:
            flash(
                "Only attendees with an Accepted RSVP can upload photos.",
                "danger"
            )
            return redirect(url_for("upload_event_photo"))

        # -----------------------------
        # Prevent Duplicate Upload
        # -----------------------------
        response = photos_table.scan()

        for photo in response.get("Items", []):

            if (
                photo["event_id"] == event_id
                and photo["uploaded_by"] == session["user"]
            ):
                flash(
                    "You have already uploaded a photo for this event.",
                    "warning"
                )
                return redirect(url_for("view_event_photos"))

        # -----------------------------
        # Validate File
        # -----------------------------
        photo = request.files.get("photo")

        if photo is None or photo.filename == "":
            flash("Please choose an image.", "danger")
            return redirect(url_for("upload_event_photo"))

        filename = secure_filename(photo.filename)

        # -----------------------------
        # Upload to S3
        # -----------------------------
        s3_key = f"event-photos/{uuid.uuid4()}_{filename}"

        s3.upload_fileobj(
            photo,
            Config.S3_BUCKET_NAME,
            s3_key
        )

        photo_url = (
            f"https://{Config.S3_BUCKET_NAME}.s3."
            f"{Config.AWS_REGION}.amazonaws.com/{s3_key}"
        )

        # -----------------------------
        # Save in DynamoDB
        # -----------------------------
        photos_table.put_item(
            Item={
                "photo_id": str(uuid.uuid4()),
                "event_id": event_id,
                "event_name": event["event_name"],
                "uploaded_by": session["user"],
                "photo_url": photo_url,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )

        flash("Photo uploaded successfully!", "success")

        return redirect(url_for("view_event_photos"))

    return render_template(
        "upload_event_photo.html",
        title="Upload Event Photo",
        events=events
    )

# --------------------------------------------------
# VIEW EVENT PHOTOS
# --------------------------------------------------

@app.route("/event-photos")
def view_event_photos():

    if "user" not in session:
        return redirect(url_for("login"))

    photos = photos_table.scan().get("Items", [])

    return render_template(
        "event_photos.html",
        photos=photos,
        title="Event Photos"
    )

# --------------------------------------------------
# PROFILE
# --------------------------------------------------

@app.route("/profile")
def profile():

    if "user" not in session:
        return redirect(url_for("login"))

    try:

        response = client.get_user(
            AccessToken=session["token"]
        )

        user_data = {}

        for attr in response["UserAttributes"]:
            user_data[attr["Name"]] = attr["Value"]

        return render_template(
            "profile.html",
            title="Profile",
            email=user_data.get("email", ""),
            first_name=user_data.get("given_name", ""),
            last_name=user_data.get("family_name", "")
        )

    except Exception as e:

        flash("Unable to load profile.", "danger")
        print(e)

        return redirect(url_for("dashboard"))


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully.", "success")

    return redirect(url_for("login"))


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
