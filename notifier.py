# -*- coding: utf8 -*-
import ast
import time
import json
import random
import platform
import configparser
from datetime import datetime

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


config = configparser.ConfigParser()
config.read('config.ini')

USERNAME = config['CRED']['USERNAME']
PASSWORD = config['CRED']['PASSWORD']
# SCHEDULE_ID = config['CRED']['SCHEDULE_ID']
MY_SCHEDULE_DATE = config['CRED']['MY_SCHEDULE_DATE']
SLOT_PREFERENCE_ORDER = ast.literal_eval(config['CRED']['SLOT_PREFERENCE_ORDER'])
print('SLOT_PREFERENCE_ORDER:', SLOT_PREFERENCE_ORDER)
# COUNTRY_CODE = config['CRED']['COUNTRY_CODE']
# FACILITY_ID = config['CRED']['FACILITY_ID']

SENDGRID_API_KEY = config['SENDGRID']['SENDGRID_API_KEY']
PUSH_TOKEN = config['PUSHOVER']['PUSH_TOKEN']
PUSH_USER = config['PUSHOVER']['PUSH_USER']

LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

REGEX_PAYMENTS = "//a[contains(text(),'Payments')]"
REGEX_SHOPPING = "//a[contains(text(),'Shopping')]"
REGEX_CHECKOUT = "//a[contains(text(),'Checkout')]"


# def MY_CONDITION(month, day): return int(month) == 11 and int(day) >= 5
def MY_CONDITION(month, day): return True # No custom condition wanted for the new scheduled date

STEP_TIME = 0.5  # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60*10  # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60*30  # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60*60  # wait time when temporary banned (empty list): 60 minutes

ACTIVITY_URL = f"https://bookings.better.org.uk/location/swiss-cottage-leisure-centre/squash-court-40min/{MY_SCHEDULE_DATE}/by-time"
EXIT = False


def get_driver():
    if LOCAL_USE:
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    else:
        dr = webdriver.Remote(command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())
    return dr

driver = get_driver()


def login():
    # Bypass reCAPTCHA
    driver.get(f"https://myaccount.better.org.uk/login")
    time.sleep(STEP_TIME)
    do_login_action()


def do_login_action():
    print("\tinput email")

    user = Wait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div[2]/div/div/form/div[1]/div/input'))
    )
    user.click()
    user.send_keys(USERNAME)
    # time.sleep(random.randint(1, 3))

    print("\tinput pwd")
    pw = driver.find_element(By.XPATH, '//*[@id="root"]/div[2]/div/div/form/div[2]/div/div/input')
    pw.click()
    pw.send_keys(PASSWORD)
    # time.sleep(random.randint(1, 3))

    print("\tsubmit")
    btn = driver.find_element(By.XPATH, '//*[@id="root"]/div[2]/div/div/form/div[3]/button')
    btn.click()
    time.sleep(random.randint(1, 3))

    Wait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, REGEX_PAYMENTS)))
    print("\tlogin successful!")


def get_available_slots_for_the_day():
    driver.get(ACTIVITY_URL)
    if not is_logged_in():
        login()
        return get_available_slots_for_the_day()
    else:
        Wait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div[3]/div/div[1]/div/div[5]')))
        time.sleep(random.randint(3, 5))
        slots_table = driver.find_element(By.XPATH, '//*[@id="root"]/div[3]/div/div[1]/div/div[5]')
        print(slots_table)
        print('slots table size:', len(slots_table.find_elements(By.XPATH, './div')))
        slots = slots_table.find_elements(By.XPATH, './div')
        # print(slots)
        # print('slots', slots.text)
        available_slots = {}
        for i, elem in enumerate(slots):
            try:
                class_time = elem.find_element(By.CLASS_NAME, 'jsQbPF')
                # print('CLASS TIME:', class_time.text)
                available_slots[class_time.text] = elem
            except:
                print("No Class time found")

        print('available_slots:', len(available_slots), [*available_slots])
        return available_slots


def get_matched_slots():
    available_slots = get_available_slots_for_the_day()
    matched_slots = {i: available_slots[i] for i in SLOT_PREFERENCE_ORDER if i in available_slots.keys()}
    print('matched_slots:', [*matched_slots])
    print(SLOT_PREFERENCE_ORDER[0], [*available_slots][0], len(SLOT_PREFERENCE_ORDER[0]), len([*available_slots][0]))
    print(SLOT_PREFERENCE_ORDER[0] == [*available_slots][0])
    return matched_slots


def book_slot(slot: str, web_element=None):
    '''
    # Below is the Code to navigate through the slot selection. This can currently circumvented by direct link
    print("Booking the slot:", slot)
    print("web_element:", web_element.text)
    book_button = web_element.find_element(By.CLASS_NAME, 'fQvmgf')
    print("book_button:", book_button.text)
    book_button.click()
    Wait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '/html/body/div[3]/div[3]/div[2]/button[1]')))

    '''
    slot_url = ACTIVITY_URL + '/slot/' + slot.replace(" ", "")
    print('slot_url:', slot_url)

    driver.get(slot_url)
    Wait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, "//button[contains(concat(' ', normalize-space(@class), ' '), 'lfRJfj')]")))
    time.sleep(random.randint(1, 3))

    btn = driver.find_element(By.XPATH, "//button[contains(concat(' ', normalize-space(@class), ' '), 'lfRJfj')]")
    print("Book now button identified")
    if btn.is_enabled():
        print('button is enabled')
    else:
        try:
            choose_available_court()
        except StaleElementReferenceException:
            return False
    btn.click()
    # Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, REGEX_CHECKOUT)))
    time.sleep(10)
    time.sleep(random.randint(1, 3))

    credit_balance_button = driver.find_element(By.XPATH, '//*[@id="root"]/div[3]/div/div[1]/div/div[3]/div/button')
    credit_balance_button.click()
    time.sleep(15)

    pay_now_button = driver.find_element(By.XPATH, '//*[@id="root"]/div[3]/div/div[1]/div/div[4]/div/div/div[2]/button')
    pay_now_button.click()
    time.sleep(5)
    print("Booking done (better cross check)")

    time.sleep(30)
    return True


def choose_available_court():
    court_selector = driver.find_element(By.CLASS_NAME, 'igKTXz')
    court_selector.click()
    time.sleep(5)
    options_dropdown = driver.find_element(By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), 'menu')]")
    print('options_dropdown:', options_dropdown.text)
    options = options_dropdown.find_elements(By.XPATH, './div/div')
    # options = select.options
    print(type(options))
    print(len(options))
    # court_selector.click()
    for index, elem in enumerate(options[::-1]):
        # TODO: refine Logic to change courts until it matches availability
        # court_selector.click()
        print(index, elem.text)
        elem.click()
        time.sleep(5)
        btn = driver.find_element(By.XPATH, "//button[contains(concat(' ', normalize-space(@class), ' '), 'lfRJfj')]")
        court_selector.click()
        if btn.is_enabled():
            print("Book Now button is enabled")
            return
        else:
            print("Book Now button is not enabled")
            court_selector.click()


def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True


if __name__ == "__main__":
    try:
        login()
        # matched_slots = get_matched_slots()
        matched_slots = SLOT_PREFERENCE_ORDER
        if len(matched_slots) != 0:
            slot = next(iter(matched_slots))
            book_slot(slot)
    finally:
        driver.quit()

    login()
    retry_count = 0
    while 1:
        if retry_count > 6:
            break
        try:
            print("------------------")
            print(datetime.today())
            print(f"Retry count: {retry_count}")
            print()

            matched_slots = SLOT_PREFERENCE_ORDER
            if len(matched_slots) != 0:
                slot = next(iter(matched_slots))
                EXIT = book_slot(slot)


            if EXIT:
                break
            else:
                print("No slot found. Snoozing for:", RETRY_TIME)
                time.sleep(RETRY_TIME)

        except:
            retry_count += 1
            print("Exception encountered. Snoozing for:", EXCEPTION_TIME, ";retry_count:", retry_count)
            time.sleep(EXCEPTION_TIME)

