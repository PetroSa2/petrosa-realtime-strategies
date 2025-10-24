class MessageProcessor:
    def __init__(self, publisher_queue):
        self.publisher_queue = publisher_queue
        self.messages_processed = 0
        self.signals_generated = 0
        self.errors_count = 0
