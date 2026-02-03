import { test, expect } from '@playwright/test';

test.describe('Landing Page', () => {
    test('should load and display hero section', async ({ page }) => {
        await page.goto('/');

        // Check page title
        await expect(page).toHaveTitle(/MeetChi/);

        // Check hero heading
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

        // Check "進入應用" button exists
        const enterButton = page.getByRole('link', { name: /進入應用/ });
        await expect(enterButton).toBeVisible();
    });

    test('should navigate to dashboard when clicking enter button', async ({ page }) => {
        await page.goto('/');

        // Click enter button
        await page.getByRole('link', { name: /進入應用/ }).click();

        // Should navigate to dashboard
        await expect(page).toHaveURL('/dashboard');
    });

    test('should display feature cards', async ({ page }) => {
        await page.goto('/');

        // Check feature cards are visible (matching actual page text)
        await expect(page.getByText('即時語音轉錄')).toBeVisible();
        await expect(page.getByText('AI 智慧摘要')).toBeVisible();
        await expect(page.getByText('說話者識別')).toBeVisible();
    });

    test('should have responsive navigation', async ({ page }) => {
        await page.goto('/');

        // Logo should be visible
        await expect(page.locator('text=MeetChi').first()).toBeVisible();
    });
});
