/**
 * The one-line count that sits under a library heading.
 *
 * Its own module because the two clients had drifted on it and the web's copy
 * was wrong: the JSX read
 *
 * ```
 * {n} {isNovelMode ? "novel" : "series"}
 * {n === 1 ? "" : "s"} {isNovelMode ? "on your shelf" : "followed"}
 * ```
 *
 * which pluralises by appending an "s" — correct for "novel", but "series" is
 * already its own plural, so every shelf with more than one follow on it read
 * "22 seriess followed". A ternary spread across three JSX expressions is
 * exactly the shape a reviewer's eye slides over, so the rule lives here as one
 * function with a test rather than inline in the markup.
 *
 * Matches `dashboard_screen.dart`'s `countLine`, which is where the correct
 * wording comes from.
 */
export function shelfCountLine(count: number, novels: boolean): string {
  if (novels) {
    return `${count} ${count === 1 ? "novel" : "novels"} on your shelf`;
  }
  return `${count} series followed`;
}
