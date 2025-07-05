from telethon import TelegramClient, events, functions
from telethon.tl.types import User, Chat, Channel
from telethon.tl.types import KeyboardButton, KeyboardButtonCallback, ReplyInlineMarkup
from typing import Optional, List, Dict, Any
from .config import APP_ID, APP_HASH
from .db import SubscriptionDB
from .subscription_manager import ChannelSubscriptionManager
import asyncio
import random
import re
import time

class BotHandler:
    def __init__(self, phone: str, session_name: str = 'session_name'):
        self.phone = phone
        self.client = TelegramClient(
            session_name,
            APP_ID,
            APP_HASH,
            device_model="Desktop",
            system_version="Windows",
            app_version="1.0",
            lang_code="en",
            system_lang_code="en"
        )
        self.selected_bot = None
        self.last_message = None
        self.last_buttons = None
        self.mode = None
        self.subscribed_channels = set()  
        self.db = SubscriptionDB(f"subscriptions_{phone.replace('+', '')}.db")  
        self.last_subscription_message = None  
        self.last_subscription_buttons = None  
        self.subscription_processing = False  
        self.global_wait_until = 0  
        self.subscription_blocked = False  
        self.processing_lock = False  
        self.sub_manager = ChannelSubscriptionManager(self)

    async def init(self):
        """Инициализация обработчика и базы данных"""
        await self.db.init_db()
        print("[БД] База данных подписок инициализирована")

    async def get_bot_list(self) -> List[Dict[str, Any]]:
        """Получить список всех ботов из диалогов"""
        try:
            dialogs = await self.client.get_dialogs()
            bots = []
            
            for dialog in dialogs:
                entity = dialog.entity
                if isinstance(entity, User) and entity.bot:
                    bots.append({
                        'id': entity.id,
                        'username': entity.username,
                        'first_name': entity.first_name,
                        'entity': entity
                    })
            
            return bots
        except Exception as e:
            print(f"Ошибка при получении списка ботов: {e}")
            return []

    async def select_bot(self) -> Optional[User]:
        """Выбор бота из списка"""
        try:
            bots = await self.get_bot_list()
            
            if not bots:
                print("Боты не найдены в ваших диалогах!")
                return None
            
            print("\nДоступные боты:")
            for i, bot in enumerate(bots):
                username = f"@{bot['username']}" if bot['username'] else "Без username"
                name = bot['first_name'] or "Без имени"
                print(f"{i + 1}. {name} ({username}) - ID: {bot['id']}")
            
            while True:
                try:
                    choice = int(input("\nВыберите номер бота: ")) - 1
                    if 0 <= choice < len(bots):
                        self.selected_bot = bots[choice]['entity']
                        print(f"Выбран бот: {bots[choice]['first_name']}")
                        return self.selected_bot
                    else:
                        print("Неверный выбор. Попробуйте снова.")
                except ValueError:
                    print("Введите число.")
        except Exception as e:
            print(f"Ошибка при выборе бота: {e}")
            return None

    async def send_start_command(self) -> bool:
        """Отправить команду /start выбранному боту"""
        try:
            if not self.selected_bot:
                print("Бот не выбран!")
                return False
            
            print(f"Отправляем /start боту {self.selected_bot.first_name}...")
            message = await self.client.send_message(self.selected_bot, '/start')
            print("Команда /start отправлена успешно!")
            return True
        except Exception as e:
            print(f"Ошибка при отправке команды /start: {e}")
            return False

    def extract_buttons(self, message) -> List[Dict[str, Any]]:
        """Извлечь кнопки из сообщения"""
        buttons = []
        try:
            if hasattr(message, 'reply_markup') and message.reply_markup:
                markup = message.reply_markup
                if hasattr(markup, 'rows'):
                    for row_idx, row in enumerate(markup.rows):
                        for btn_idx, button in enumerate(row.buttons):
                            button_data = {
                                'row': row_idx,
                                'column': btn_idx,
                                'text': button.text if hasattr(button, 'text') else 'Без текста'
                            }
                            
                            if hasattr(button, 'data'):
                                button_data['callback_data'] = button.data
                                button_data['type'] = 'callback'
                            elif hasattr(button, 'url'):
                                button_data['url'] = button.url
                                button_data['type'] = 'url'
                            else:
                                button_data['type'] = 'unknown'
                            
                            buttons.append(button_data)
        except Exception as e:
            print(f"Ошибка при извлечении кнопок: {e}")
        
        return buttons

    def display_message_info(self, message, buttons: List[Dict[str, Any]]):
        """Отобразить информацию о сообщении и кнопках"""
        print("\n" + "="*50)
        print("ОТВЕТ ОТ БОТА:")
        print("="*50)
        
        if hasattr(message, 'message') and message.message:
            print(f"Текст: {message.message}")
        else:
            print("Текст: (пустое сообщение)")
        
        if buttons:
            print("\nКнопки:")
            for i, btn in enumerate(buttons):
                btn_type = btn.get('type', 'unknown')
                if btn_type == 'callback':
                    print(f"{i + 1}. {btn['text']} (callback)")
                elif btn_type == 'url':
                    print(f"{i + 1}. {btn['text']} (URL: {btn.get('url', 'N/A')})")
                else:
                    print(f"{i + 1}. {btn['text']} ({btn_type})")
        else:
            print("\nКнопки отсутствуют")
        
    async def click_button(self, button_index: int) -> bool:
        """Нажать на кнопку по индексу"""
        try:
            if not self.last_message or not self.last_buttons:
                print("Нет доступных кнопок для нажатия!")
                return False
            
            if button_index < 0 or button_index >= len(self.last_buttons):
                print(f"Неверный индекс кнопки! Доступно кнопок: {len(self.last_buttons)}")
                return False
            
            button = self.last_buttons[button_index]
            
            if button['type'] == 'callback':
                print(f"Нажимаем кнопку: {button['text']}")
                await self.last_message.click(data=button['callback_data'])
                print("Кнопка нажата успешно!")
                return True
            elif button['type'] == 'url':
                print(f"Это URL кнопка: {button['url']}")
                print("URL кнопки нельзя 'нажать', но вы можете открыть ссылку в браузере.")
                return False
            elif button['type'] == 'unknown':
                
                print(f"Нажимаем inline кнопку: {button['text']}")
                row = button['row']
                column = button['column']
                await self.last_message.click(row, column)
                print("Inline кнопка нажата успешно!")
                return True
            else:
                print(f"Неподдерживаемый тип кнопки: {button['type']}")
                return False
                
        except Exception as e:
            print(f"Ошибка при нажатии кнопки: {e}")
            return False

    async def handle_bot_response(self, event):
        """Handle incoming messages from the selected bot"""
        try:
            message = event.message
            print("\n=== Сообщение от бота ===")
            print(f"Текст: {message.text}")
            
            
            buttons = self.extract_buttons(message)
            
            
            self.last_message = message
            self.last_buttons = buttons
            
            if buttons:
                self.display_message_info(message, buttons)
                
                
                choice = input("\nХотите нажать на кнопку? (y/n): ").lower()
                if choice == 'y':
                    try:
                        button_num = int(input("Введите номер кнопки: ")) - 1
                        await self.click_button(button_num)
                    except ValueError:
                        print("Введите корректный номер кнопки")
            else:
                print("Кнопки не найдены")
                
        except Exception as e:
            print(f"Ошибка при обработке ответа бота: {e}")

    def select_mode(self) -> str:
        """Выбор режима работы"""
        print("\nВыберите режим работы:")
        print("1. Ручной режим")
        print("2. Автоматический режим (gram_piarbot)")
        
        while True:
            try:
                choice = int(input("\nВведите номер режима: "))
                if choice == 1:
                    return "manual"
                elif choice == 2:
                    return "auto"
                else:
                    print("Неверный выбор. Попробуйте снова.")
            except ValueError:
                print("Введите число.")

    async def auto_gram_piarbot_sequence(self):
        """Автоматическая последовательность для gram_piarbot"""
        try:
            
            await self.init()
            
            
            print("[АВТО] Поиск бота @gram_piarbot в диалогах...")
            dialogs = await self.client.get_dialogs()
            gram_piarbot = None
            
            for dialog in dialogs:
                entity = dialog.entity
                if isinstance(entity, User) and entity.username == "gram_piarbot":
                    gram_piarbot = entity
                    break
            
            if not gram_piarbot:
                print("[АВТО] Бот @gram_piarbot не найден в диалогах!")
                return False
            
            self.selected_bot = gram_piarbot
            print(f"[АВТО] Найден бот: {gram_piarbot.first_name} (@{gram_piarbot.username})")
            
            
            print("[АВТО] Отправляем команду /start...")
            await self.client.send_message(gram_piarbot, '/start')
            print("[АВТО] Команда /start отправлена, ожидаем ответ...")
            
            
            response_received = False
            
            
            @self.client.on(events.NewMessage(chats=[gram_piarbot.id]))
            async def auto_handle_message(event):
                nonlocal response_received
                response_received = True
                await self.auto_handle_bot_response(event)
            
            
            @self.client.on(events.MessageEdited(chats=[gram_piarbot.id]))
            async def auto_handle_edited_message(event):
                await self.auto_handle_bot_response(event)
            
            
            await asyncio.sleep(5)
            
            if not response_received:
                print("[АВТО] Нет ответа на /start, возможно язык уже выбран. Отправляем '👨‍💻 Заработать'...")
                await self.client.send_message(gram_piarbot, '👨‍💻 Заработать')
                print("[АВТО] Сообщение '👨‍💻 Заработать' отправлено")
            
            print("[АВТО] Автоматический режим запущен для @gram_piarbot")
            await self.client.run_until_disconnected()
            return True
            
        except Exception as e:
            print(f"[АВТО] Ошибка в автоматическом режиме: {e}")
            return False

    def _print_channel_buttons(self, buttons: List[Dict[str, Any]]):
        """Вывод структуры кнопок каналов"""
        print("Кнопки каналов:")
        for btn in buttons:
            print(f"ROW: {btn.get('row')} COL: {btn.get('column')} TEXT: {btn.get('text')} TYPE: {btn.get('type')} URL: {btn.get('url', '')}")

    async def auto_handle_bot_response(self, event):
        """Упрощённая автоматическая обработка сообщений (без подписок)"""
        message = event.message
        buttons = self.extract_buttons(message)
        self.last_message = message
        self.last_buttons = buttons

        # Если появились кнопки каналов – выводим структуру и выходим
        if any(btn.get('type') == 'url' and ('t.me/' in btn.get('url', '') or 'telegram.me/' in btn.get('url', '')) for btn in buttons):
            self._print_channel_buttons(buttons)
            await self.sub_manager.process_channel_buttons(buttons)
            return

        # Автовыбор языка
        for i, btn in enumerate(buttons):
            if 'русский' in btn.get('text', '').lower():
                await asyncio.sleep(2)
                await self.click_button(i)
                return

        # Кнопка "Заработать"
        for i, btn in enumerate(buttons):
            if 'заработать' in btn.get('text', '').lower() or '👨‍💻' in btn.get('text', ''):
                await asyncio.sleep(2)
                await self.click_button(i)
                return

        # Кнопка "Подписаться на канал"
        for i, btn in enumerate(buttons):
            if 'подписаться' in btn.get('text', '').lower() and 'канал' in btn.get('text', '').lower() and btn.get('type') == 'callback':
                await asyncio.sleep(2)
                await self.click_button(i)
                return

    async def handle_channel_subscriptions(self, buttons: List[Dict[str, Any]]):
        """Автоматическая подписка на каналы и проверка подписки"""
        try:
            
            current_time = time.time()
            if self.subscription_blocked and current_time < self.global_wait_until:
                remaining_time = int(self.global_wait_until - current_time)
                print(f"[АВТО] Подписки заблокированы еще на {remaining_time} секунд, пропускаем обработку")
                return
            elif self.subscription_blocked and current_time >= self.global_wait_until:
                print("[АВТО] Время блокировки истекло, снимаем блокировку подписок")
                self.subscription_blocked = False
                self.global_wait_until = 0
            
            channel_check_pairs = []
            navigation_buttons = []
            
            
            rows = {}
            for btn in buttons:
                row_idx = btn.get('row', 0)
                if row_idx not in rows:
                    rows[row_idx] = []
                rows[row_idx].append(btn)
            
            
            for row_idx, row_buttons in rows.items():
                url_buttons = [btn for btn in row_buttons if btn.get('type') == 'url']
                check_buttons = [btn for btn in row_buttons if btn.get('type') == 'callback' and 
                                ('проверить' in btn['text'].lower() or '🔄' in btn['text'])]
                
                
                if url_buttons and check_buttons:
                    
                    url_buttons.sort(key=lambda x: x.get('column', 0))
                    check_buttons.sort(key=lambda x: x.get('column', 0))
                    
                    
                    for i, url_btn in enumerate(url_buttons):
                        
                        check_idx = min(i, len(check_buttons) - 1) if check_buttons else None
                        check_btn = check_buttons[check_idx] if check_idx is not None else None
                        
                        
                        url_idx = buttons.index(url_btn)
                        check_idx = buttons.index(check_btn) if check_btn else None
                        
                        channel_check_pairs.append({
                            'channel': {'index': url_idx, 'url': url_btn.get('url', ''), 'text': url_btn['text']},
                            'check': {'index': check_idx, 'text': check_btn['text']} if check_idx is not None else None
                        })
                        
                        print(f"[АВТО] Найден канал для подписки: {url_btn['text']} - {url_btn.get('url', '')}")
                        if check_idx is not None:
                            print(f"[АВТО] Найдена соответствующая кнопка проверки: {check_btn['text']}")
            
            
            for i, btn in enumerate(buttons):
                if btn.get('type') == 'callback' and (btn['text'] in ['>', '<', '→', '←'] or 
                     'next' in btn['text'].lower() or 'prev' in btn['text'].lower()):
                    navigation_buttons.append({'index': i, 'text': btn['text']})
                    print(f"[АВТО] Найдена кнопка навигации: {btn['text']}")
            
            
            for pair in channel_check_pairs:
                channel_info = pair['channel']
                check_info = pair['check']
                
                
                if not channel_info.get('url'):
                    print(f"[АВТО] Отсутствует URL для канала {channel_info['text']}, пропускаем")
                    continue
                
                url = channel_info['url']
                
                
                wait_time = await self.db.get_wait_time(self.phone, url)
                if wait_time > 0:
                    print(f"[АВТО] Для канала {channel_info['text']} действует ограничение по времени: {wait_time} сек., пропускаем")
                    continue
                
                
                is_subscribed = await self.check_channel_subscription(url)
                
                if not is_subscribed:
                    print(f"[АВТО] Не подписаны на канал {channel_info['text']}, подписываемся...")
                    
                    
                    subscription_result = await self.subscribe_to_channel(channel_info)
                    
                    if subscription_result is not True:
                        print(f"[АВТО] Подписка на канал {channel_info['text']} не удалась: {subscription_result}")
                        
                        
                        wait_seconds = 0
                        if isinstance(subscription_result, str):
                            
                            wait_match = re.search(r'wait of (\d+) seconds', subscription_result, re.IGNORECASE)
                            if wait_match:
                                wait_seconds = int(wait_match.group(1))
                                print(f"[АВТО] Обнаружено ограничение по времени: {wait_seconds} секунд")
                        
                        
                        await self.db.add_subscription_attempt(
                            self.phone, 
                            url, 
                            success=False, 
                            error_message=str(subscription_result) if subscription_result else None,
                            wait_time=wait_seconds
                        )
                        
                        
                        if wait_seconds > 0:
                            print(f"[АВТО] Обнаружено временное ограничение на подписки на {wait_seconds} секунд")
                            self.global_wait_until = time.time() + wait_seconds
                            self.subscription_blocked = True
                            self.subscription_processing = False
                            print(f"[АВТО] Установлена глобальная блокировка подписок до {time.strftime('%H:%M:%S', time.localtime(self.global_wait_until))}")
                            return
                        
                        continue
                    else:
                        print(f"[АВТО] Успешно подписались на канал {channel_info['text']}")
                else:
                    print(f"[АВТО] Уже подписаны на канал {channel_info['text']}")
                
                
                if check_info:
                    print("[АВТО] Ожидание 5 секунд перед проверкой подписки...")
                    await asyncio.sleep(5)
                    print(f"[АВТО] Нажимаем кнопку проверки: {check_info['text']}")
                    success = await self.click_button(check_info['index'])
                    if success:
                        print(f"[АВТО] Кнопка проверки '{check_info['text']}' нажата успешно")
                        await asyncio.sleep(8)  
                    else:
                        print(f"[АВТО] Ошибка при нажатии кнопки проверки {check_info['text']}")
                
                
                if pair != channel_check_pairs[-1]:  
                    delay = random.randint(30, 60)
                    print(f"[АВТО] Ожидание {delay} секунд перед следующей подпиской...")
                    await asyncio.sleep(delay)
            
            
            if navigation_buttons and channel_check_pairs:
                print("[АВТО] Обработка страницы завершена. Ищем кнопку для перехода на следующую страницу...")
                next_button = None
                for nav_btn in navigation_buttons:
                    if nav_btn['text'] in ['>', '→'] or 'next' in nav_btn['text'].lower():
                        next_button = nav_btn
                        break
                
                if next_button:
                    print(f"[АВТО] Переходим на следующую страницу: {next_button['text']}")
                    await asyncio.sleep(5)
                    success = await self.click_button(next_button['index'])
                    if success:
                        print(f"[АВТО] Кнопка '{next_button['text']}' нажата успешно")
                else:
                    print("[АВТО] Кнопка для перехода на следующую страницу не найдена")
                    print("[АВТО] Завершаем обработку подписок - больше нет страниц")
                    self.subscription_processing = False
                    self.last_subscription_message = None
                    self.last_subscription_buttons = None
            else:
                print("[АВТО] Нет каналов для подписки на этой странице")
                self.subscription_processing = False
                self.last_subscription_message = None
                self.last_subscription_buttons = None
                    
        except Exception as e:
            print(f"[АВТО] Ошибка при обработке подписок на каналы: {e}")
            self.subscription_processing = False
            self.last_subscription_message = None
            self.last_subscription_buttons = None

    async def handle_channel_subscriptions_with_check(self, subscription_buttons: List[Dict[str, Any]], check_buttons: List[Dict[str, Any]]):
        """Обработка подписок с отдельными кнопками проверки"""
        try:
            
            current_time = time.time()
            if self.subscription_blocked and current_time < self.global_wait_until:
                remaining_time = int(self.global_wait_until - current_time)
                print(f"[АВТО] Подписки заблокированы еще на {remaining_time} секунд, пропускаем обработку")
                return
            elif self.subscription_blocked and current_time >= self.global_wait_until:
                print("[АВТО] Время блокировки истекло, снимаем блокировку подписок")
                self.subscription_blocked = False
                self.global_wait_until = 0

            
            check_button_indices = []
            for i, btn in enumerate(check_buttons):
                if btn.get('type') == 'callback' and ('проверить' in btn['text'].lower() or '🔄' in btn['text']):
                    check_button_indices.append(i)
                    print(f"[АВТО] Найдена кнопка проверки: {btn['text']} (индекс: {i})")

            
            if check_button_indices:
                check_index = check_button_indices[0]
                check_btn = check_buttons[check_index]
                print(f"[АВТО] Нажимаем кнопку проверки: {check_btn['text']}")
                success = await self.click_button(check_index)
                if success:
                    print(f"[АВТО] Кнопка проверки '{check_btn['text']}' нажата успешно")
                    await asyncio.sleep(8)  
                else:
                    print(f"[АВТО] Ошибка при нажатии кнопки проверки {check_btn['text']}")
            else:
                print("[АВТО] Кнопки проверки не найдены")
                
                await self.handle_channel_subscriptions(subscription_buttons)
                
        except Exception as e:
            print(f"[АВТО] Ошибка при обработке подписок с проверкой: {e}")
            self.subscription_processing = False
            self.last_subscription_message = None
            self.last_subscription_buttons = None

    async def check_channel_subscription(self, url: str) -> bool:
        """Проверить, подписан ли бот на канал через Telegram API"""
        try:
            
            if '/+' in url or 'joinchat/' in url:
                
                
                return False
            
            
            channel_username = self.extract_channel_username(url)
            if not channel_username:
                return False
            
            try:
                channel_entity = await self.client.get_entity(channel_username)

                await self.client(functions.channels.GetParticipantRequest(
                    channel=channel_entity,
                    participant='me'
                ))
                print(f"[АВТО] Уже подписан на канал: {channel_username}")
                
                
                await self.db.add_subscription(self.phone, url, channel_username)
                
                return True
            except Exception:
                
                return False
                
        except Exception as e:
            print(f"[АВТО] Ошибка при проверке подписки: {e}")
            return False

    async def subscribe_to_channel(self, channel_info: Dict[str, Any]):
        """Подписка на конкретный канал"""
        try:
            url = channel_info.get('url')
            channel_name = channel_info.get('text')
            
            if not url:
                print(f"[АВТО] Отсутствует URL для канала {channel_name}")
                return False
            
            if url in self.subscribed_channels:
                print(f"[АВТО] Канал {channel_name} уже обработан в этой сессии, пропускаем")
                return True
            
            print(f"[АВТО] Подписываемся на канал: {channel_name}")
            
            
            if '/+' in url or 'joinchat/' in url:
                invite_hash = self.extract_invite_hash(url)
                if invite_hash:
                    try:
                        print(f"[АВТО] Попытка присоединения к каналу по приглашению: {channel_name}")
                        
                        await asyncio.wait_for(
                            self.client(functions.messages.ImportChatInviteRequest(invite_hash)),
                            timeout=30.0
                        )
                        print(f"[АВТО] Успешно присоединились к каналу по приглашению: {channel_name}")
                        self.subscribed_channels.add(url)
                        
                        
                        await self.db.add_subscription(self.phone, url, channel_name)
                        await self.db.add_subscription_attempt(self.phone, url, success=True)
                        
                        return True
                    except asyncio.TimeoutError:
                        print(f"[АВТО] Таймаут при присоединении к каналу {channel_name}")
                        self.subscribed_channels.add(url)
                        return False
                    except Exception as invite_error:
                        error_str = str(invite_error)
                        print(f"[АВТО] Ошибка при присоединении по приглашению {channel_name}: {invite_error}")
                        self.subscribed_channels.add(url)
                        return error_str if "wait" in error_str.lower() else False
            
            
            channel_username = self.extract_channel_username(url)
            if not channel_username:
                print(f"[АВТО] Не удалось извлечь имя канала из URL: {url}")
                return False
            
            try:
                print(f"[АВТО] Получение информации о канале: {channel_username}")
                channel_entity = await asyncio.wait_for(
                    self.client.get_entity(channel_username),
                    timeout=15.0
                )
                
                print(f"[АВТО] Попытка подписки на канал: {channel_name}")
                await asyncio.wait_for(
                    self.client(functions.channels.JoinChannelRequest(channel_entity)),
                    timeout=30.0
                )
                print(f"[АВТО] Успешно подписались на канал: {channel_name} (@{channel_username})")
                self.subscribed_channels.add(url)
                
                
                await self.db.add_subscription(self.phone, url, channel_name)
                await self.db.add_subscription_attempt(self.phone, url, success=True)
                
                return True
                
            except asyncio.TimeoutError:
                print(f"[АВТО] Таймаут при подписке на канал {channel_name}")
                self.subscribed_channels.add(url)
                return False
            except Exception as join_error:
                error_str = str(join_error)
                print(f"[АВТО] Ошибка при подписке на канал {channel_name}: {join_error}")
                self.subscribed_channels.add(url)
                if "wait" in error_str.lower():
                    
                    wait_match = re.search(r'wait of (\d+) seconds', error_str)
                    if wait_match:
                        wait_seconds = int(wait_match.group(1))
                        print(f"[АВТО] Установка глобальной блокировки на {wait_seconds} секунд")
                        self.subscription_blocked = True
                        self.global_wait_until = time.time() + wait_seconds
                    return error_str
                return False
                    
        except Exception as e:
            print(f"[АВТО] Ошибка при подписке на канал: {e}")
            return False

    def extract_channel_username(self, url: str) -> Optional[str]:
        """Извлечь имя канала из URL"""
        try:
            
            if 't.me/' in url:
                username = url.split('t.me/')[-1]
            elif 'telegram.me/' in url:
                username = url.split('telegram.me/')[-1]
            else:
                return None
            
            
            if username.startswith('+') or 'joinchat/' in username:
                return None
            
            
            username = username.split('?')[0].split('/')[0]
            
            
            if not username.startswith('@'):
                username = '@' + username
                
            return username
        except Exception as e:
            print(f"[АВТО] Ошибка при извлечении имени канала: {e}")
            return None
    
    def extract_invite_hash(self, url: str) -> Optional[str]:
        """Извлечь хеш приглашения из URL"""
        try:
            if '/+' in url:
                
                hash_part = url.split('/+')[-1]
            elif 'joinchat/' in url:
                
                hash_part = url.split('joinchat/')[-1]
            else:
                return None
            
            
            invite_hash = hash_part.split('?')[0].split('/')[0]
            return invite_hash
        except Exception as e:
            print(f"[АВТО] Ошибка при извлечении хеша приглашения: {e}")
            return None

    async def start(self):
        try:
            print("Запуск клиента...")
            await self.client.start(phone=self.phone)
            print("Успешный вход!")

            
            self.mode = self.select_mode()
            
            if self.mode == "auto":
                
                await self.auto_gram_piarbot_sequence()
            else:
                
                selected_bot = await self.select_bot()
                if not selected_bot:
                    print("Бот не выбран. Выход...")
                    return

                
                await self.send_start_command()

                
                @self.client.on(events.NewMessage(chats=[selected_bot.id]))
                async def handle_message(event):
                    await self.handle_bot_response(event)

                print(f"Ожидание сообщений от бота {selected_bot.first_name}...")
                await self.client.run_until_disconnected()
            
        except Exception as e:
            print(f"Ошибка в методе start: {e}")
        finally:
            if hasattr(self, 'db'):
                await self.db.close()

    def run(self):
        try:
            self.client.loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            print("\nКлиент остановлен пользователем")
            
            if hasattr(self, 'db'):
                self.client.loop.run_until_complete(self.db.close())
        except Exception as e:
            print(f"Ошибка запуска клиента: {e}")
        finally:
            self.client.disconnect()
