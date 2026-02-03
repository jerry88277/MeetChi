import { test, expect } from '@playwright/test';

test.describe('Dashboard Page', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('/dashboard');
    });

    test('should display sidebar with MeetChi logo', async ({ page }) => {
        // Check sidebar logo
        await expect(page.locator('.bg-slate-900').first()).toBeVisible();
        await expect(page.getByText('MeetChi').first()).toBeVisible();
    });

    test('should show backend connection status in sidebar', async ({ page }) => {
        // Check for connection status section
        const statusSection = page.locator('text=後端狀態');
        await expect(statusSection).toBeVisible();

        // Should show either "已連線" or "未連線"
        const connectedText = page.locator('text=已連線');
        const disconnectedText = page.locator('text=未連線');

        // One of them should be visible
        const isConnected = await connectedText.isVisible();
        const isDisconnected = await disconnectedText.isVisible();
        expect(isConnected || isDisconnected).toBe(true);
    });

    test('should display page header with title', async ({ page }) => {
        await expect(page.getByRole('heading', { name: '我的會議記錄' })).toBeVisible();
        await expect(page.getByText('管理並搜尋所有的會議內容')).toBeVisible();
    });

    test('should have search input', async ({ page }) => {
        const searchInput = page.getByPlaceholder(/搜尋會議標題/);
        await expect(searchInput).toBeVisible();

        // Test search functionality
        await searchInput.fill('測試');
        await expect(searchInput).toHaveValue('測試');
    });

    test('should have action buttons', async ({ page }) => {
        // Check refresh button
        await expect(page.getByRole('button', { name: /重新整理/ })).toBeVisible();

        // Check start recording button
        await expect(page.getByRole('button', { name: /開始錄音/ })).toBeVisible();
    });

    test('should show empty state when no meetings', async ({ page }) => {
        // Wait for loading to complete
        await page.waitForLoadState('networkidle');

        // If no meetings, should show empty state message
        const emptyMessage = page.getByText(/還沒有會議記錄|沒有找到符合的會議記錄/);
        const meetingCards = page.locator('[class*="MeetingCard"]');

        // Either show empty state or meeting cards
        const hasEmptyMessage = await emptyMessage.isVisible().catch(() => false);
        const hasMeetingCards = await meetingCards.count() > 0;

        expect(hasEmptyMessage || hasMeetingCards).toBe(true);
    });

    test('should navigate to settings when clicking settings menu', async ({ page }) => {
        // Click settings in sidebar
        await page.getByRole('button', { name: /系統設定/ }).click();

        // Should show settings view
        await expect(page.getByRole('heading', { name: '系統設定' })).toBeVisible();
    });
});

test.describe('Dashboard - Recording Flow', () => {
    test('should switch to recording view when clicking start recording', async ({ page }) => {
        await page.goto('/dashboard');

        // Click start recording button
        await page.getByRole('button', { name: /開始錄音/ }).click();

        // Should show recording view
        await expect(page.getByText('正在錄音')).toBeVisible();
    });

    test('should display timer in recording view', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /開始錄音/ }).click();

        // Timer should start at 00:00
        await expect(page.getByText(/00:0[0-9]/)).toBeVisible();

        // Wait and check timer increments
        await page.waitForTimeout(1500);
        await expect(page.getByText(/00:0[1-9]/)).toBeVisible();
    });

    test('should show audio visualizer bars', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /開始錄音/ }).click();

        // Should have visualizer bars (w-2 bg-indigo-500 rounded-full)
        const bars = page.locator('.bg-indigo-500.rounded-full.w-2');
        await expect(bars.first()).toBeVisible();
    });

    test('should return to dashboard when stopping recording', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /開始錄音/ }).click();

        // Wait for recording view
        await expect(page.getByText('正在錄音')).toBeVisible();

        // Click stop button (large red square button)
        await page.locator('button.bg-red-500').click();

        // Should show saving state or return to dashboard/detail
        // (API call may fail in test environment, so accept both outcomes)
        await expect(
            page.getByRole('heading', { name: '我的會議記錄' })
                .or(page.getByText('儲存中...'))
                .or(page.getByText('儲存會議失敗'))
        ).toBeVisible({ timeout: 10000 });
    });

    test('should return to dashboard when canceling recording', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /開始錄音/ }).click();

        // Wait for recording view
        await expect(page.getByText('正在錄音')).toBeVisible();

        // Click cancel button (X button)
        await page.locator('button.bg-slate-100').click();

        // Should return to dashboard
        await expect(page.getByRole('heading', { name: '我的會議記錄' })).toBeVisible();
    });
});

test.describe('Dashboard - Settings View', () => {
    test('should show API connection settings', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /系統設定/ }).click();

        // Should show Backend URL section
        await expect(page.getByText('Backend URL')).toBeVisible();

        // Should have readonly input with API URL
        const urlInput = page.locator('input[readonly]').first();
        await expect(urlInput).toBeVisible();
        const value = await urlInput.inputValue();
        expect(value).toContain('http');
    });

    test('should show connection status', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /系統設定/ }).click();

        // Should show Online/Offline status
        const onlineStatus = page.getByText('Online');
        const offlineStatus = page.getByText('Offline');

        const hasOnline = await onlineStatus.isVisible().catch(() => false);
        const hasOffline = await offlineStatus.isVisible().catch(() => false);

        expect(hasOnline || hasOffline).toBe(true);
    });

    test('should show speech recognition settings', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /系統設定/ }).click();

        // Should show speech settings
        await expect(page.getByText('語音辨識設定')).toBeVisible();
        await expect(page.getByText('自動標點符號')).toBeVisible();
        await expect(page.getByText('說話者分離')).toBeVisible();
    });

    test('should return to dashboard when clicking back', async ({ page }) => {
        await page.goto('/dashboard');
        await page.getByRole('button', { name: /系統設定/ }).click();

        // Click back button
        await page.locator('button').filter({ has: page.locator('.rotate-180') }).first().click();

        // Should return to dashboard
        await expect(page.getByRole('heading', { name: '我的會議記錄' })).toBeVisible();
    });
});
