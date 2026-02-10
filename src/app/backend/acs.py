from fastapi import Request
from fastapi.responses import JSONResponse, Response
from azure.core.messaging import CloudEvent
from azure.eventgrid import EventGridEvent
from azure.communication.callautomation import (
    CallAutomationClient,
    PhoneNumberIdentifier,
    MediaStreamingOptions,
    MediaStreamingTransportType,
    MediaStreamingContentType,
    MediaStreamingAudioChannelType,
    AudioFormat)

class AcsCaller:
    source_number: str
    acs_connection_string: str
    acs_callback_path: str
    websocket_url: str
    media_streaming_configuration: MediaStreamingOptions

    def __init__(self, source_number:str, acs_connection_string: str, acs_callback_path: str, acs_media_streaming_websocket_path: str):
        self.source_number = source_number
        self.acs_connection_string = acs_connection_string
        self.acs_callback_path = acs_callback_path
        self.media_streaming_configuration = MediaStreamingOptions(
            transport_url=acs_media_streaming_websocket_path,
            transport_type=MediaStreamingTransportType.WEBSOCKET,
            content_type=MediaStreamingContentType.AUDIO,
            audio_channel_type=MediaStreamingAudioChannelType.MIXED,
            start_media_streaming=True,
            enable_bidirectional=True,
            audio_format=AudioFormat.PCM24_K_MONO
        )

    async def initiate_call(self, target_number: str):
        self.call_automation_client = CallAutomationClient.from_connection_string(self.acs_connection_string)
        self.target_participant = PhoneNumberIdentifier(target_number)
        self.source_caller = PhoneNumberIdentifier(self.source_number)
        self.call_automation_client.create_call(
            self.target_participant,
            self.acs_callback_path,
            media_streaming=self.media_streaming_configuration,
            source_caller_id_number=self.source_caller
        )

    async def answer_inbound_call(self, incoming_call_context: str):
        self.call_automation_client = CallAutomationClient.from_connection_string(self.acs_connection_string)
        self.call_automation_client.answer_call(
            incoming_call_context,
            self.acs_callback_path,
            media_streaming=self.media_streaming_configuration
        )

    async def outbound_call_handler(self, request: Request):
        cloudevent = await request.json()
        for event_dict in cloudevent:
            event = CloudEvent.from_dict(event_dict)
            if event.data is None:
                continue

            call_connection_id = event.data['callConnectionId']
            print(f"{event.type} event received for call connection id: {call_connection_id}")

            if event.type == "Microsoft.Communication.CallConnected":
                print("Call connected")

        return Response(status_code=200)

    async def inbound_call_handler(self, request: Request):
        # Check if this is an Event Grid validation request
        if request.headers.get('aeg-event-type') == 'SubscriptionValidation':
            data = await request.json()
            validation_code = data[0]['data']['validationCode']
            return JSONResponse(content={
                'validationResponse': validation_code
            })

        # Handle incoming call events
        try:
            event_data = await request.json()
            print(f"Received event data: {event_data}")

            # EventGrid sends events in an array
            for event_dict in event_data:
                print(f"Processing event: {event_dict}")
                event = EventGridEvent.from_dict(event_dict)

                if event.event_type == "Microsoft.Communication.IncomingCall":
                    print(f"Incoming call event data: {event.data}")
                    incoming_call_context = event.data['incomingCallContext']
                    await self.answer_inbound_call(incoming_call_context)
                    print("Incoming call answered")
                    return Response(status_code=200)

        except Exception as e:
            print(f"Error handling inbound call: {str(e)}")
            return Response(status_code=500, content=str(e))

        return Response(status_code=200)
