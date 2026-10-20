import { isValidElement, type ReactElement } from "react";

import RootLayout, { metadata } from "@/app/layout";

test("wraps every page in an English document", () => {
  const page = <p>page</p>;
  const html = RootLayout({ children: page }) as ReactElement<{ lang: string; children: ReactElement<{ children: unknown }> }>;
  expect(isValidElement(html)).toBe(true);
  expect(html.type).toBe("html");
  expect(html.props.lang).toBe("en");
  expect(html.props.children.props.children).toBe(page);
});

test("names the page", () => {
  expect(metadata.title).toBe("commentary-sync studio");
});
