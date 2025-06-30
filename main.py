from bot.handler import BotHandler
import sys
import hashlib
import os
import json


SAVED_PHONES_FILE = 'saved_phones.json'

def get_session_name(phone):
    
    
    return f"session_{hashlib.md5(phone.encode()).hexdigest()[:8]}"

def load_saved_phones():
    
    if os.path.exists(SAVED_PHONES_FILE):
        try:
            with open(SAVED_PHONES_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_phone(phone):
    
    phones = load_saved_phones()
    if phone not in phones:
        phones.append(phone)
        with open(SAVED_PHONES_FILE, 'w') as f:
            json.dump(phones, f)

def select_phone():
    
    saved_phones = load_saved_phones()
    
    if saved_phones:
        print("\nСохраненные номера телефонов:")
        for i, phone in enumerate(saved_phones):
            print(f"{i+1}. {phone}")
        print(f"{len(saved_phones)+1}. Ввести другой номер")
        
        while True:
            try:
                choice = int(input("\nВыберите номер (введите цифру): "))
                if 1 <= choice <= len(saved_phones):
                    return saved_phones[choice-1]
                elif choice == len(saved_phones)+1:
                    break
                else:
                    print("Неверный выбор. Попробуйте снова.")
            except ValueError:
                print("Введите число.")
    
    
    phone = input("Введите номер телефона (например, +79964626164): ")
    save_phone(phone)
    return phone

def main():
    
    if len(sys.argv) < 2:
        phone = select_phone()
    else:
        phone = sys.argv[1]
        save_phone(phone)  

    
    session_name = get_session_name(phone)
    handler = BotHandler(phone, session_name)
    handler.run()

if __name__ == "__main__":
    main()
