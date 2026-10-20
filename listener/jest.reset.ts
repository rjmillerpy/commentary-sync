import { reset as resetAudio } from "./__tests__/_fakeAudio";
import { reset as resetNetwork } from "./__tests__/_fakeNetwork";
import { reset as resetSecureStore } from "./__tests__/_fakeSecureStore";
import { reset as resetVideo } from "./__tests__/_fakeVideo";

beforeEach(() => {
  resetSecureStore();
  resetVideo();
  resetAudio();
  resetNetwork();
});
