from typing import List, Dict, Any, Optional
import asyncio
import random
import re
import time

from telethon import functions


class ChannelSubscriptionManager:
    """Простая обработка кнопок подписки и проверки"""

    def __init__(self, bot_handler):
        self.bot = bot_handler
        
        self.sub_delay_range = (12, 22)
        self.check_delay_range = (5, 9)

    
    def __getattr__(self, name):
        return getattr(self.bot, name)

    

    async def handle_channel_subscriptions(self, buttons: List[Dict[str, Any]]):
        """Автоматическая подписка на каналы и проверка подписки"""
        
        print("[DEBUG] Структура кнопок (row/column/text/type/url):")
        for btn in buttons:
            print(f"ROW: {btn.get('row')} COL: {btn.get('column')} TEXT: {btn.get('text')} TYPE: {btn.get('type')} URL: {btn.get('url', '')}")

        try:
            current_time = time.time()
            if self.subscription_blocked and current_time < self.global_wait_until:
                remaining_time = int(self.global_wait_until - current_time)
                print(f"[АВТО] Подписки заблокированы еще на {remaining_time} секунд, пропускаем обработку")
                return
            elif self.subscription_blocked and current_time >= self.global_wait_until:
                print(f"[АВТО] Время блокировки истекло, снимаем блокировку подписок")
                self.subscription_blocked = False
                self.global_wait_until = 0

            channel_check_pairs = []
            navigation_buttons = []

            rows: Dict[int, List[Dict[str, Any]]] = {}
            for btn in buttons:
                row_idx = btn.get('row', 0)
                rows.setdefault(row_idx, []).append(btn)

            for row_idx, row_buttons in rows.items():
                url_buttons = [btn for btn in row_buttons if btn.get('type') == 'url']
                check_buttons = [btn for btn in row_buttons if btn.get('type') == 'callback' and (
                    'проверить' in btn['text'].lower() or '🔄' in btn['text'])]

                if url_buttons and check_buttons:
                    url_buttons.sort(key=lambda x: x.get('column', 0))
                    check_buttons.sort(key=lambda x: x.get('column', 0))

                    for i, url_btn in enumerate(url_buttons):
                        check_idx_rel = min(i, len(check_buttons) - 1) if check_buttons else None
                        check_btn = check_buttons[check_idx_rel] if check_idx_rel is not None else None

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
                    print(f"[АВТО] Ожидание 5 секунд перед проверкой подписки...")
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
                print(f"[АВТО] Обработка страницы завершена. Ищем кнопку для перехода на следующую страницу...")
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
                    print(f"[АВТО] Кнопка для перехода на следующую страницу не найдена")
                    print(f"[АВТО] Завершаем обработку подписок - больше нет страниц")
                    self.subscription_processing = False
                    self.last_subscription_message = None
                    self.last_subscription_buttons = None
            else:
                print(f"[АВТО] Нет каналов для подписки на этой странице")
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
                print(f"[АВТО] Время блокировки истекло, снимаем блокировку подписок")
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
                await self.client(functions.channels.GetParticipantRequest(channel=channel_entity, participant='me'))
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
                        await asyncio.wait_for(self.client(functions.messages.ImportChatInviteRequest(invite_hash)), timeout=30.0)
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
                        return error_str if 'wait' in error_str.lower() else False

            channel_username = self.extract_channel_username(url)
            if not channel_username:
                print(f"[АВТО] Не удалось извлечь имя канала из URL: {url}")
                return False

            try:
                print(f"[АВТО] Получение информации о канале: {channel_username}")
                channel_entity = await asyncio.wait_for(self.client.get_entity(channel_username), timeout=15.0)

                print(f"[АВТО] Попытка подписки на канал: {channel_name}")
                await asyncio.wait_for(self.client(functions.channels.JoinChannelRequest(channel_entity)), timeout=30.0)
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
                if 'wait' in error_str.lower():
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

    async def process_channel_buttons(self, buttons: List[Dict[str, Any]]):
        """Подписаться на каналы (левая колонка), затем проверка (правая)."""
        
        rows = {}
        for idx, btn in enumerate(buttons):
            row = btn.get('row', 0)
            rows.setdefault(row, []).append((idx, btn))

        
        ordered_rows = sorted(rows.items())

        
        for _, btns in ordered_rows:
            
            btns_sorted = sorted(btns, key=lambda x: x[1].get('column', 0))
            url_btn = next((b for b in btns_sorted if b[1].get('type') == 'url'), None)
            check_btn = next((b for b in btns_sorted if b[1].get('type') == 'callback'), None)
            if not url_btn:
                continue

            channel_info = {
                'index': url_btn[0],
                'url': url_btn[1].get('url', ''),
                'text': url_btn[1].get('text', '')
            }
            print(f"▶ Подписка: {channel_info['text']}")
            result = await self.subscribe_to_channel(channel_info)

            
            if isinstance(result, str) and 'wait' in result.lower():
                wait_match = re.search(r'wait of (\d+)', result)
                if wait_match:
                    wait_sec = int(wait_match.group(1)) + 5
                    print(f"⏳ Ожидание {wait_sec} сек. из-за лимита")
                    await asyncio.sleep(wait_sec)
                    
                    continue

            if check_btn:
                print(f"🔄 Проверка индекса {check_btn[0]}")
                await self.click_button(check_btn[0])
                await asyncio.sleep(random.randint(*self.check_delay_range))

            await asyncio.sleep(random.randint(*self.sub_delay_range)) 