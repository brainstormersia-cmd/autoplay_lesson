const puppeteer = require('puppeteer');

const COURSE_URL =
  process.env.COURSE_URL ||
  'https://www.coursera.org/learn/high-stakes-leadership/lecture/xKTQO/deepwater-horizon-setting-the-stage';
const SPEED_MULTIPLIER = 2;
const SAFETY_BUFFER_MS = 8000;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const parseMinutes = (text) => {
  if (!text) {
    return null;
  }
  const match = text.match(/(\d+)\s*minute/i);
  if (!match) {
    return null;
  }
  return Number.parseInt(match[1], 10);
};

const isDisabledItem = async (item) =>
  item.evaluate((node) => {
    const anchor = node.querySelector('a');
    return (
      node.getAttribute('aria-disabled') === 'true' ||
      node.classList.contains('disabled') ||
      (anchor && anchor.getAttribute('aria-disabled') === 'true')
    );
  });

const getVideoItems = async (page) => {
  const listItems = await page.$$('li');
  const videos = [];

  for (const item of listItems) {
    let typeLabel = null;
    try {
      typeLabel = await item.$eval('div.css-1rhvk9j', (el) => el.textContent.trim());
    } catch (error) {
      continue;
    }

    if (!typeLabel.includes('Video')) {
      continue;
    }

    const isCompleted = await item.$('svg[data-testid="learn-item-success-icon"]');
    if (isCompleted) {
      continue;
    }

    const hasUnpresented = await item.$('rect');
    if (!hasUnpresented) {
      continue;
    }

    let durationText = null;
    try {
      durationText = await item.$eval(
        'span.rc-A11yScreenReaderOnly',
        (el) => el.textContent,
      );
    } catch (error) {
      durationText = null;
    }

    const durationMinutes = parseMinutes(durationText);
    const link = await item.$('a.css-1oaf');

    if (!link) {
      continue;
    }

    videos.push({ item, link, durationMinutes });
  }

  return videos;
};

const run = async () => {
  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
  });
  const page = await browser.newPage();

  await page.goto(COURSE_URL, { waitUntil: 'networkidle2' });

  const videos = await getVideoItems(page);

  for (let index = 0; index < videos.length; index += 1) {
    const { item, link, durationMinutes } = videos[index];

    const disabled = await isDisabledItem(item);
    if (disabled) {
      continue;
    }

    if (!durationMinutes) {
      continue;
    }

    const waitMs = (durationMinutes * 60 * 1000) / SPEED_MULTIPLIER + SAFETY_BUFFER_MS;

    await link.click();
    await delay(waitMs);

    if (index < videos.length - 1) {
      await page.goBack({ waitUntil: 'networkidle2' });
    }
  }

  await browser.close();
};

run().catch((error) => {
  // eslint-disable-next-line no-console
  console.error('Errore durante l\'esecuzione:', error);
  process.exitCode = 1;
});
