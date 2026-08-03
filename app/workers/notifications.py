from app.services.communication_providers import MockEmailProvider, MockNotificationProvider

def providers():
    return MockNotificationProvider(), MockEmailProvider()
