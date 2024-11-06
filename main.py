import os
import imaplib
import email
import logging
import time
from typing import List
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('unsubscribe.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class UnsubscribeLink:
    url: str
    email_subject: str
    sender: str
    method: str  # 'link' or 'button'

class EmailUnsubscribe:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('EMAIL')
        self.password = os.getenv('PASSWORD')
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993

        if not all([self.username, self.password]):
            raise ValueError("Email credentials not found in .env file")

    def connect_mail(self) -> imaplib.IMAP4_SSL:
        """Establish connection to email server"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.username, self.password)
            mail.select('inbox')
            return mail
        except Exception as e:
            logging.error(f"Failed to connect to email: {str(e)}")
            raise

    def extract_unsubscribe_links(self, html_content: str, subject: str, sender: str) -> List[UnsubscribeLink]:
        """Extract unsubscribe links from email HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []

        # Check for links containing "unsubscribe"
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text().lower()
            if any(word in text.lower() or word in href.lower()
                   for word in ['unsubscribe', 'opt-out', 'opt out']):
                links.append(UnsubscribeLink(
                    url=href,
                    email_subject=subject,
                    sender=sender,
                    method='link'
                ))

        return links

    def process_email_content(self, msg: email.message.Message) -> List[UnsubscribeLink]:
        """Process email message and extract unsubscribe links"""
        links = []
        subject = msg.get('subject', '')
        sender = msg.get('from', '')

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode()
                    links.extend(self.extract_unsubscribe_links(html_content, subject, sender))
        else:
            if msg.get_content_type() == "text/html":
                html_content = msg.get_payload(decode=True).decode()
                links.extend(self.extract_unsubscribe_links(html_content, subject, sender))

        return links

    def search_unsubscribe_emails(self) -> List[UnsubscribeLink]:
        """Search emails for unsubscribe links"""
        mail = self.connect_mail()
        links = []

        try:
            _, search_data = mail.search(None, '(BODY "unsubscribe")')
            email_ids = search_data[0].split()

            for num in email_ids:
                try:
                    _, msg_data = mail.fetch(num, "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    links.extend(self.process_email_content(msg))
                except Exception as e:
                    logging.error(f"Error processing email {num}: {str(e)}")

        except Exception as e:
            logging.error(f"Error searching emails: {str(e)}")
        finally:
            mail.logout()

        return links

    def unsubscribe_via_selenium(self, link: UnsubscribeLink) -> bool:
        """Handle unsubscribe using Selenium for interactive pages"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Remove for debugging
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        try:
            service = Service()  # Update path as needed
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(link.url)

            # Wait for and find unsubscribe elements
            wait = WebDriverWait(driver, 10)
            unsubscribe_elements = []

            # Check for various unsubscribe elements
            selectors = [
                (By.XPATH, "//button[contains(translate(., 'UNSUBSCRIBE', 'unsubscribe'), 'unsubscribe')]"),
                (By.XPATH, "//a[contains(translate(., 'UNSUBSCRIBE', 'unsubscribe'), 'unsubscribe')]"),
                (By.XPATH, "//input[@type='submit'][contains(translate(@value, 'UNSUBSCRIBE', 'unsubscribe'), 'unsubscribe')]")
            ]

            for by, selector in selectors:
                try:
                    element = wait.until(EC.element_to_be_clickable((by, selector)))
                    unsubscribe_elements.append(element)
                except TimeoutException:
                    continue

            if unsubscribe_elements:
                unsubscribe_elements[0].click()
                time.sleep(2)  # Wait for confirmation
                return True

            return False

        except Exception as e:
            logging.error(f"Selenium error for {link.url}: {str(e)}")
            return False
        finally:
            driver.quit()

    def unsubscribe_via_requests(self, link: UnsubscribeLink) -> bool:
        """Handle simple unsubscribe links via requests"""
        try:
            response = requests.get(link.url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logging.error(f"Request error for {link.url}: {str(e)}")
            return False

    def process_unsubscribe_links(self, links: List[UnsubscribeLink]):
        """Process all unsubscribe links"""
        results = []

        for link in links:
            logging.info(f"Processing unsubscribe for {link.sender} - {link.email_subject}")

            # Try requests first for simple links
            success = self.unsubscribe_via_requests(link)

            # If requests fails, try Selenium
            if not success:
                success = self.unsubscribe_via_selenium(link)

            results.append({
                'sender': link.sender,
                'subject': link.email_subject,
                'url': link.url,
                'success': success
            })

        # Save results
        self.save_results(results)

    def save_results(self, results: List[dict]):
        """Save unsubscribe results to a file"""
        with open("unsubscribe_results.txt", "w") as f:
            for result in results:
                status = "Success" if result['success'] else "Failed"
                f.write(f"{status} - {result['sender']} - {result['subject']}\n")

def main():
    try:
        unsubscriber = EmailUnsubscribe()
        links = unsubscriber.search_unsubscribe_emails()
        unsubscriber.process_unsubscribe_links(links)
    except Exception as e:
        logging.error(f"Main execution error: {str(e)}")

if __name__ == "__main__":
    main()