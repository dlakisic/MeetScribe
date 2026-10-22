/**
 * Shared application state for the MeetScribe dashboard.
 */

const state = {
    selectedMeetingId: null,
    transcriptData: null,
    meetingData: null,
    meetings: [],
    pollTimers: new Map(),
    jobProgress: new Map(), // meetingId -> { label, percent } while processing
    audioReady: Promise.resolve(),
    askResult: null,
};

export default state;
