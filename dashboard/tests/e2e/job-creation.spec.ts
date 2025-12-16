/**
 * IT-Friends Handwerk Dashboard - Job Creation E2E Tests
 *
 * Tests for the job creation form and workflow.
 */

import { test, expect } from "@playwright/test";

test.describe("Aufgabe erstellen", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to tasks page
    await page.goto("/aufgaben");
  });

  test("should navigate to creation form from tasks list", async ({ page }) => {
    // Click "Neue Aufgabe" button
    await page.click('a:has-text("Neue Aufgabe")');

    // Verify navigation to creation page
    await expect(page).toHaveURL("/aufgaben/neu");
    await expect(page.locator("h1")).toContainText("Neue Aufgabe erstellen");
  });

  test("should show validation errors for required fields", async ({ page }) => {
    // Navigate directly to creation page
    await page.goto("/aufgaben/neu");

    // Try to proceed without filling required fields
    await page.click('button:has-text("Weiter")');

    // Check for validation error on customer name
    await expect(
      page.locator("text=Kundenname muss mindestens 2 Zeichen haben")
    ).toBeVisible();
  });

  test("should complete step 1 with customer information", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Fill customer information (Step 1)
    await page.fill('input[name="customer_name"]', "Test Kunde GmbH");
    await page.fill('input[name="customer_phone"]', "+49 7471 12345");
    await page.fill('input[name="customer_email"]', "test@kunde.de");

    // Fill address
    await page.fill('input[name="address_street"]', "Teststraße");
    await page.fill('input[name="address_number"]', "123");
    await page.fill('input[name="address_zip"]', "72379");
    await page.fill('input[name="address_city"]', "Hechingen");

    // Click next step
    await page.click('button:has-text("Weiter")');

    // Verify we're on step 2 (Auftragsdetails)
    await expect(page.locator("h3:has-text('Auftragsdetails')")).toBeVisible();
  });

  test("should complete step 2 with job details", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Complete Step 1
    await page.fill('input[name="customer_name"]', "Test Kunde");
    await page.click('button:has-text("Weiter")');

    // Fill job details (Step 2)
    await page.fill('input[name="title"]', "Heizung funktioniert nicht");
    await page.fill(
      'textarea[name="description"]',
      "Die Heizung ist seit heute morgen ausgefallen. Keine Wärme im ganzen Haus."
    );

    // Select trade category
    await page.click('[name="trade_category"]');
    await page.click('text=SHK');

    // Select urgency
    await page.click('[name="urgency"]');
    await page.click('text=Dringend');

    // Click next step
    await page.click('button:has-text("Weiter")');

    // Verify we're on step 3 (Überprüfung)
    await expect(page.locator("h3:has-text('Zusammenfassung')")).toBeVisible();
  });

  test("should show summary on step 3 before submission", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Complete Step 1
    await page.fill('input[name="customer_name"]', "Familie Weber");
    await page.fill('input[name="customer_phone"]', "+49 7471 54321");
    await page.fill('input[name="address_zip"]', "72379");
    await page.fill('input[name="address_city"]', "Hechingen");
    await page.click('button:has-text("Weiter")');

    // Complete Step 2
    await page.fill('input[name="title"]', "Wasserrohrbruch im Keller");
    await page.fill(
      'textarea[name="description"]',
      "Wasser läuft aus dem Rohr im Keller. Haupthahn ist abgedreht."
    );
    await page.click('button:has-text("Weiter")');

    // Verify summary shows customer info
    await expect(page.locator("text=Familie Weber")).toBeVisible();
    await expect(page.locator("text=+49 7471 54321")).toBeVisible();
    await expect(page.locator("text=72379 Hechingen")).toBeVisible();

    // Verify summary shows job info
    await expect(page.locator("text=Wasserrohrbruch im Keller")).toBeVisible();
  });

  test("should allow navigation back through steps", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Complete Step 1
    await page.fill('input[name="customer_name"]', "Test Kunde");
    await page.click('button:has-text("Weiter")');

    // Verify on Step 2
    await expect(page.locator("h3:has-text('Auftragsdetails')")).toBeVisible();

    // Go back to Step 1
    await page.click('button:has-text("Zurück")');

    // Verify back on Step 1 with data preserved
    await expect(page.locator("h3:has-text('Kundeninformation')")).toBeVisible();
    await expect(page.locator('input[name="customer_name"]')).toHaveValue(
      "Test Kunde"
    );
  });

  test("should cancel and return to tasks list", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Click cancel button
    await page.click('button:has-text("Abbrechen")');

    // Verify navigation back to tasks list
    await expect(page).toHaveURL("/aufgaben");
  });

  test("should validate PLZ format (5 digits)", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Fill customer name (required)
    await page.fill('input[name="customer_name"]', "Test Kunde");

    // Enter invalid PLZ (not 5 digits)
    await page.fill('input[name="address_zip"]', "123");

    // Try to proceed
    await page.click('button:has-text("Weiter")');

    // Check for validation error
    await expect(page.locator("text=PLZ muss 5 Ziffern haben")).toBeVisible();
  });

  test("should validate email format", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Fill customer name
    await page.fill('input[name="customer_name"]', "Test Kunde");

    // Enter invalid email
    await page.fill('input[name="customer_email"]', "invalid-email");

    // Try to proceed
    await page.click('button:has-text("Weiter")');

    // Check for validation error
    await expect(page.locator("text=Ungültige E-Mail-Adresse")).toBeVisible();
  });
});

test.describe("Aufgabe erstellen - Accessibility", () => {
  test("should be keyboard navigable", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Tab to first input
    await page.keyboard.press("Tab");

    // Verify focus is on customer name input
    const focusedElement = page.locator(":focus");
    await expect(focusedElement).toHaveAttribute("name", "customer_name");

    // Fill with keyboard
    await page.keyboard.type("Test Kunde");

    // Tab to next field
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveAttribute("name", "customer_phone");
  });

  test("should show required field indicators", async ({ page }) => {
    await page.goto("/aufgaben/neu");

    // Check for required indicator on customer name
    const customerNameLabel = page.locator('label:has-text("Kundenname")');
    await expect(customerNameLabel.locator("text=*")).toBeVisible();
  });
});
