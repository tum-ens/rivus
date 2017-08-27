import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def email_me(message, sender, send_pass, recipient, smtp_addr, smtp_port,
             subject='[rivus][notification]'):
    """Send notification message through email server.

    Parameters
    ----------
    message : str
        Body of the e-mail
    sender : str
        The e-mail account through which the email will be sent.
        E.g. tum.robot@gmail.com
    send_pass : str
        Password of sender. Hopefully read from a file,
        which is not added to Git...
    recipient : str
        The e-mail account of you, where you want to get the notification.
    smtp_addr : str
        SMTP Address. Like "smtp.gmail.com"
    smtp_port : int
        SMTP Port. Like 587
    subject : str, optional
        The subject of the mail...

    Returns
    -------
    integer
        0  - if run through without exception
        -1 - if encountered with a problem (mainly for unittest)
    """
    smtp_msg = MIMEMultipart()
    smtp_msg['From'] = sender
    smtp_msg['To'] = recipient
    smtp_msg['Subject'] = subject

    mailServer = smtplib.SMTP(smtp_addr, smtp_port)
    try:
        mailServer.ehlo()
        mailServer.starttls()
        mailServer.ehlo()
        mailServer.login(sender, send_pass)
    except Exception as email_error:
        print(email_error)
        return -1
    else:
        if not isinstance(message, str):
            message = repr(message)
        smtp_msg.attach(MIMEText(message))
        mailServer.sendmail(sender, recipient, smtp_msg.as_string())
        mailServer.close()
        return 0
