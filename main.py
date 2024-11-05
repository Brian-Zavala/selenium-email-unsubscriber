import os
import imaplib
import email
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

username = os.getenv('EMAIL')
password = os.getenv('PASSWORD')

def connect_mail():
    # Create a IMAP(Internet Message Access Protocol)-to manage with ssl(Secure Sockets Layer)-to send
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)

    # Authenticate
    mail.login(username, password)
    mail.select('inbox')
    return mail

def extract_links_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    links = [link["href"] for link in soup.find_all('a', href=True) if "unsubscribe" in link["href"].lower()]
    return links

def click_link(link):
    try:
        response = requests.get(link)
        if response.status_code == 200:
            print("Successful link")
        else:
            print("Failed link", link, "error code", response.status_code)
    except Exception as e:
        print("Error with", link, str(e))

def search_email():
    """Search emails for matching criteria
    Common criteria are 'All', 'UNSEEN', 'SEEN', 'From "someone@example.com"'
    """
    # Select mailbox type
    mail = connect_mail()

    # Search for mail
    _, search_mail = mail.search(None, '(BODY "unsubscribe")')
    data = search_mail[0].split()

    links = []

    for num in data:
        _, data = mail.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                   html_content = part.get_payload(decode=True).decode()
                   links.extend(extract_links_html(html_content))
        else:
            content_type = msg.get_content_type()
            content = msg.get_payload(decode=True)

            if content_type == "text/html":
                links.extend(extract_links_html(content))

    mail.logout()
    return links

def save_links(links):
    with open("links.txt", "w") as f:
        f.write("\n".join(links))

links = search_email()

for link in links:
    click_link(link)

save_links(links)