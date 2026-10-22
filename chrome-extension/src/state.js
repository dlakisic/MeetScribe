/**
 * Shared application state for the MeetScribe dashboard.
 */

const state = {
    selectedMeetingId: null,
    transcriptData: null,
    meetingData: null,
    meetings: [],
    pollTimers: new Map(),
    audioReady: Promise.resolve(),
    askResult: null,
};

export default state;
