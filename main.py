class Messages:
    """ All the bot reply messages ans promtpts """

    # ------------------------------------------------------------------------------
    SYSTEM_PROMPT = """You are a text formatting expert. Your job:

1. Add proper punctuation and capitalization
2. Break text into readable paragraphs
3. Fix obvious grammar/spelling errors
4. Keep the exact same meaning and tone
5. Remove unnecessary emojis
6. If no TLDR exists, add one at the end

IMPORTANT: Return only the improved text. No explanations."""

    # ------------------------------------------------------------------------------
    BEAUTIFIED_RESPONSE = """Beautified !!

---

{beautified_text}

---

Improved by BeautifyBot
*I'm a bot that improves post readability!* """

    # ------------------------------------------------------------------------------
    DUPLICATE_RESPONSE_1 = """I've already beautified this post! 

---

**[Here's my previous response]({existing_permalink})**

---
*I am a bot that improves post readability!*
"""

    DUPLICATE_RESPONSE_2 = """ I've previously beautified this post - scroll up to find my earlier response with the improved text.
    """

    # ------------------------------------------------------------------------------
    VALIDATION_ERROR = """Sorry, I couldn't process your post: {reason}

Requirements:
- Must be a text post
- Length between {min_length:,} - {max_length:,} characters"""

    # ------------------------------------------------------------------------------
    GENERIC_ERROR = """Sorry! I encountered an error while processing your post.
Please try again in a few minutes."""

    # ------------------------------------------------------------------------------
    VALIDATION_REASONS = {
        'not_text': "Not a text post",
        'too_short': "Too short ({length} chars)",
        'too_long': "Too long ({length} chars)"
    }

#==========================================================================================================

from contextlib import contextmanager
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
import logging
import os
import praw
import sqlite3
import time


load_dotenv()

# logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("beautify-bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("BeautifyBot")

#====================================================================================
class Config:

    # reddit
    REDDIT_CLIENT_ID = os.getenv("reddit_client_id")
    REDDIT_CLIENT_SECRET = os.getenv("reddit_client_secret")
    REDDIT_USERNAME = os.getenv("reddit_username")
    REDDIT_PASSWORD = os.getenv("reddit_password")
    REDDIT_USER_AGENT = os.getenv("reddit_user_agent")

    # BOT SETTINGS
    SUBREDDITS = "test"   # IMadeThis
    MIN_POST_LENGTH = 1000
    MAX_POST_LENGTH = 15000
    COMMENT_DELAY = 2
    RECONNECT_DELAY = 30 

    # groq
    GROQ_API_KEY = os.getenv("groq_api_key")
    GROQ_MODEL = "llama-3.1-8b-instant"

#====================================================================================
class DatabaseManager:

    def __init__(self, db_path="beautify-bot.db"):
        self.db_path = db_path
        self.setup_database()
        logger.info(f"Database initialized: {db_path}")


    @contextmanager
    def get_connection(self):
        """ context manager for database connection """
        db = sqlite3.connect(self.db_path)

        try:
            yield db
        finally:
            db.close()


    def setup_database(self):

        with self.get_connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS processed_posts (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       post_id TEXT NOT NULL UNIQUE,
                       post_title TEXT,
                       post_author TEXT,
                       reply_permalink TEXT,
                       status TEXT NOT NULL DEFAULT 'beautified'
                    )
            """)

            db.commit()

        logger.info("Databasse ready")


    def is_post_processed(self, post_id):

        with self.get_connection() as db:
            result = db.execute(
                "SELECT reply_permalink FROM processed_posts WHERE post_id = ?",(post_id,) 
            ).fetchone()

            return result[0] if result else None


    def save_processed_post(self, post_id, post_title, post_author, reply_permalink):

        with self.get_connection() as db:
            db.execute("""
                INSERT OR REPLACE INTO processed_posts(
                       post_id, post_title, post_author, reply_permalink) VALUES (?, ?, ?, ?)
            """, (post_id, post_title, post_author, reply_permalink))

            db.commit()

        logger.info(f"saved processed post: {post_id}, Title: {post_title}")

#====================================================================================
class BeautifyBot:

    def __init__(self):
        self.db = DatabaseManager()
        self.reddit = self._setup_reddit()
        self.groq = self._setup_groq()
        logger.info(f"BeautifyBot initialized.")


    def _setup_reddit(self):
        
        reddit = praw.Reddit(
            client_id = Config.REDDIT_CLIENT_ID,
            client_secret = Config.REDDIT_CLIENT_SECRET,
            username = Config.REDDIT_USERNAME,
            password = Config.REDDIT_PASSWORD,
            user_agent = Config.REDDIT_USER_AGENT
        )

        logger.info(f"Connected to reddit as:{reddit.user.me()}")
        return reddit
    
    def _setup_groq(self):

        client = Groq(api_key=Config.GROQ_API_KEY)
        logger.info(f"Connected to Groq")
        return client
    

    def run(self):
        """ main loop """

        logger.info(f"monitoring comments on {Config.SUBREDDITS} ...")

        subreddit = self.reddit.subreddit(Config.SUBREDDITS)

        while True:
            try:
                for comment in subreddit.stream.comments(skip_existing=True):
                    self._process_comment(comment)

                    time.sleep(Config.COMMENT_DELAY)

            except Exception as e:
                logger.error(f"Comment Stream error: {e}")
                logger.info(f"Reconnecting the bot in: {Config.RECONNECT_DELAY} seconds...")
                time.sleep(Config.RECONNECT_DELAY)


    def _process_comment(self, comment):

        if comment.author and comment.author.name == Config.REDDIT_USERNAME:
            return
        
        if comment.author is None:
            return
        
        if "!beautify" in comment.body.lower():
            logger.info(f"Trigger found comment id: {comment.id}")

            try:
                self._process_trigger_request(comment)

            except Exception as e:
                logger.error(f"Error processing comment: {e}")


    def beautify_with_ai(self, text_post):

        responce = self.groq.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[
                {"role":"system", "content":Messages.SYSTEM_PROMPT},
                {"role": "user", "content": f"Please improve this text:\n\n{text_post}"}
            ],
            max_tokens=6000,
            temperature=0.2
        )

        return responce.choices[0].message.content.strip()

    
    def _process_trigger_request(self, comment):
        """ main processing logic... """

        post = comment.submission
        post_id = post.id
        post_title = post.title[:80] + "..." if len(post.title) > 80 else post.title
        post_author = post.author.name if post.author else "[deleted]"

        logger.info(f"Processing the post: {post_id} \n Title:{post_title}")

        # checking if already processed
        existing_permalink = self.db.is_post_processed(post_id=post_id)

        if existing_permalink:
            self._send_duplicate_responce(comment, existing_permalink)
            return
        

        # if new post, check if its valid for further processing
        is_valid, reason = self.is_valid_post(post)

        if not is_valid:
            self._send_validation_error(comment, reason)
            return
        
        # everything is fine, process the post

        try:
            beautified_text = self.beautify_with_ai(post.selftext)
            reply_permalink = self._send_beautified_responce(comment, beautified_text)

            self.db.save_processed_post(
                post_id=post_id,
                post_title=post_title,
                post_author=post_author,
                reply_permalink=reply_permalink
            )

            logger.info(f"Post Beautified !!!, post id:{post_id}, \n Title: {post_title}")

        except Exception as e:
            logger.error(f"Error while processing triggered request: {e}")
            self._send_error_message(comment)


# ---------------message functions -------------------

    def _send_duplicate_responce(self, comment, existing_permalink):
        """ send responce if the post was already processed """

        message = Messages.DUPLICATE_RESPONSE_1.format(existing_permalink=existing_permalink)
        # message = Messages.DUPLICATE_RESPONSE_2


        comment.reply(message)
        print(message)
        logger.info("sent duplicate responce")

    
    def _send_validation_error(self, comment, reason):

        message = Messages.VALIDATION_ERROR.format(reason=reason, 
                                        min_length = Config.MIN_POST_LENGTH,
                                        max_length = Config.MAX_POST_LENGTH)

        comment.reply(message)
        logger.info(f"Sent the validation error: {reason}")


    def _send_beautified_responce(self, comment, beautified_text):

        message = Messages.BEAUTIFIED_RESPONSE.format(beautified_text=beautified_text)

        reply = comment.reply(message)
        logger.info(f"Sent Beautified post")

        if reply and reply.permalink:
            return f"https://reddit.com{reply.permalink}"
        return None
    

    def _send_error_message(self, comment):

        message = Messages.GENERIC_ERROR
        comment.reply(message)
        logger.info(f"Sent error responce")

# ---------------------------------------------------------------------

    def is_valid_post(self, post):

        if not post.selftext:   # checks if its a text post
            return False, Messages.VALIDATION_REASONS["not_text"]
        
        text_length = len(post.selftext.strip())

        if text_length < Config.MIN_POST_LENGTH:    #1000
            return False, Messages.VALIDATION_REASONS["too_short"]
        
        if text_length > Config.MAX_POST_LENGTH:    #15000
            return False, Messages.VALIDATION_REASONS["too_long"]
        
        return True, "Valid"
    

def main():

    try:
        logger.info(f"="*50)
        logger.info(f"Starting the script...")
        logger.info(f"="*50)


        bot = BeautifyBot()
        bot.run()

    except KeyboardInterrupt:
        logger.info("Bot stopped by admin")

    except Exception as e:
        logger.error(f"Encounterd Error while starting the bot: {e}")
        raise

if __name__ == "__main__":
    main()

