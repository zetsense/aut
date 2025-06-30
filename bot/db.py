import aiosqlite
from typing import List, Dict, Any

class SubscriptionDB:
    """База данных для хранения информации о подписках на каналы"""
    
    def __init__(self, db_path: str = "subscriptions.db"):
        """
        Инициализация базы данных подписок
        
        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path = db_path
        self._connection = None
        
    async def _get_connection(self) -> aiosqlite.Connection:
        """Получение соединения с базой данных"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
        return self._connection
    
    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        conn = await self._get_connection()
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            channel_url TEXT NOT NULL,
            channel_name TEXT,
            status TEXT DEFAULT 'subscribed',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(phone, channel_url)
        )
        ''')
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS subscription_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            channel_url TEXT NOT NULL,
            attempt_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            wait_time INTEGER DEFAULT 0
        )
        ''')
        await conn.commit()
    
    async def add_subscription(self, phone: str, channel_url: str, channel_name: str = None) -> bool:
        """
        Добавление информации о подписке на канал
        
        Args:
            phone: Номер телефона пользователя
            channel_url: URL канала
            channel_name: Название канала (опционально)
            
        Returns:
            bool: True если успешно добавлено, False если запись уже существует
        """
        try:
            conn = await self._get_connection()
            await conn.execute(
                'INSERT OR REPLACE INTO subscriptions (phone, channel_url, channel_name) VALUES (?, ?, ?)',
                (phone, channel_url, channel_name)
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка при добавлении подписки: {e}")
            return False
    
    async def add_subscription_attempt(self, phone: str, channel_url: str, success: bool, 
                                      error_message: str = None, wait_time: int = 0) -> bool:
        """
        Добавление информации о попытке подписки
        
        Args:
            phone: Номер телефона пользователя
            channel_url: URL канала
            success: Успешность попытки
            error_message: Сообщение об ошибке (если есть)
            wait_time: Время ожидания перед следующей попыткой (в секундах)
            
        Returns:
            bool: True если успешно добавлено
        """
        try:
            conn = await self._get_connection()
            await conn.execute(
                'INSERT INTO subscription_attempts (phone, channel_url, success, error_message, wait_time) VALUES (?, ?, ?, ?, ?)',
                (phone, channel_url, success, error_message, wait_time)
            )
            await conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка при добавлении попытки подписки: {e}")
            return False
    
    async def is_subscribed(self, phone: str, channel_url: str) -> bool:
        """
        Проверка, подписан ли пользователь на канал
        
        Args:
            phone: Номер телефона пользователя
            channel_url: URL канала
            
        Returns:
            bool: True если подписан, False если нет
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                'SELECT id FROM subscriptions WHERE phone = ? AND channel_url = ?',
                (phone, channel_url)
            )
            result = await cursor.fetchone()
            return result is not None
        except Exception as e:
            print(f"Ошибка при проверке подписки: {e}")
            return False
    
    async def get_wait_time(self, phone: str, channel_url: str) -> int:
        """
        Получение времени ожидания для канала (если есть)
        
        Args:
            phone: Номер телефона пользователя
            channel_url: URL канала
            
        Returns:
            int: Время ожидания в секундах или 0, если ожидание не требуется
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                '''
                SELECT wait_time, attempt_timestamp 
                FROM subscription_attempts 
                WHERE phone = ? AND channel_url = ? AND wait_time > 0
                ORDER BY attempt_timestamp DESC
                LIMIT 1
                ''',
                (phone, channel_url)
            )
            result = await cursor.fetchone()
            
            if result:
                wait_time, timestamp = result
                # Проверяем, истекло ли время ожидания
                # Преобразуем timestamp в секунды с начала эпохи
                import datetime
                if isinstance(timestamp, str):
                    timestamp = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
                
                current_time = datetime.datetime.now().timestamp()
                elapsed = current_time - timestamp
                
                if elapsed < wait_time:
                    return int(wait_time - elapsed)
            
            return 0
        except Exception as e:
            print(f"Ошибка при получении времени ожидания: {e}")
            return 0
    
    async def get_all_subscriptions(self, phone: str) -> List[Dict[str, Any]]:
        """
        Получение всех подписок пользователя
        
        Args:
            phone: Номер телефона пользователя
            
        Returns:
            List[Dict]: Список подписок с информацией
        """
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                'SELECT channel_url, channel_name, status, timestamp FROM subscriptions WHERE phone = ?',
                (phone,)
            )
            rows = await cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    'channel_url': row[0],
                    'channel_name': row[1],
                    'status': row[2],
                    'timestamp': row[3]
                })
            
            return result
        except Exception as e:
            print(f"Ошибка при получении всех подписок: {e}")
            return []
    
    async def close(self):
        """Закрытие соединения с базой данных"""
        if self._connection:
            await self._connection.close()
            self._connection = None
