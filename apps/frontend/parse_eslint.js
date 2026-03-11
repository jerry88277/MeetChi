const { execSync } = require('child_process');
const fs = require('fs');

try {
    execSync('npx eslint ./src/app/dashboard/page.tsx -f json', { encoding: 'utf8', stdio: 'pipe' });
    console.log("No lint errors.");
} catch (error) {
    try {
        const data = JSON.parse(error.stdout.replace(/^\[.*?\][^\n]*\n/gm, ''));
        // ^ remove any next.js warning headers before parsing
        const lines = [];
        data[0].messages.forEach(m => {
            lines.push(`Line ${m.line}:${m.column} [${m.severity === 2 ? 'ERROR' : 'WARN'}] ${m.message} (${m.ruleId})`);
        });
        fs.writeFileSync('parsed_eslint.txt', lines.join('\n'));
        console.log("Wrote parsed_eslint.txt");
    } catch (e) {
        console.error("Parse failed", e);
        fs.writeFileSync('raw_eslint_out.txt', error.stdout);
    }
}
