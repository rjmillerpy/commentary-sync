// The entry point registers App with Expo, which starts it on the phone.
// Jest only lets a mock factory use variables named mock*.
const mockRegisterRootComponent = jest.fn();
jest.mock("expo", () => ({ registerRootComponent: mockRegisterRootComponent }));

test("the app is registered as the root component", () => {
  let app: unknown;
  jest.isolateModules(() => {
    jest.requireActual("../index");
    app = jest.requireActual("@/App").default; // the same module instance index.ts loaded
  });
  expect(mockRegisterRootComponent).toHaveBeenCalledWith(app);
});
