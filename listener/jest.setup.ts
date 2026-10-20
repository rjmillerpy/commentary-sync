// The phone's boundaries, replaced for every test: its secure storage and its
// media player. Everything inside the app runs for real.
jest.mock("expo-secure-store", () => jest.requireActual("./__tests__/_fakeSecureStore"));
jest.mock("expo-video", () => jest.requireActual("./__tests__/_fakeVideo"));
// The library's own stand-in for its native module (device insets).
jest.mock("react-native-safe-area-context", () => jest.requireActual("react-native-safe-area-context/jest/mock").default);
jest.mock("expo-audio", () => jest.requireActual("./__tests__/_fakeAudio"));
jest.mock("expo-network", () => jest.requireActual("./__tests__/_fakeNetwork"));
