"""
Extract Item 1A Risk Factors from 10-K HTML files
IMPROVED VERSION - Finds all matches and selects the correct section heading
"""

import os
import re
from bs4 import BeautifulSoup
from pathlib import Path


def clean_text(text):
    """Clean extracted text"""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove non-breaking spaces
    text = text.replace('\xa0', ' ')
    # Remove extra spaces
    text = text.strip()
    return text


def score_candidate(element, text, soup):
    """
    Score a potential Item 1A heading candidate.
    Higher score = more likely to be the actual section heading.
    Returns (score, element)
    """
    score = 0

    # Check element's own text
    element_text = element.get_text(strip=True)

    # Bonus points for being a standalone element (text matches closely)
    if len(element_text) <= len(text) + 15:
        score += 50

    # Bonus for being in a heading tag
    if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        score += 30

    # Bonus for being in a paragraph (common for 10-K headings)
    if element.name in ['p', 'div']:
        score += 20

    # Penalty for being nested in inline formatting
    if element.name in ['b', 'strong', 'span', 'i', 'em']:
        score -= 20

    # Check for reference indicators in element or parent
    reference_indicators = [
        'described in', 'see', 'refer to', 'factors in', 'included in',
        'discussed in', 'contained in', 'set forth in', 'presented in',
        'disclosed in', 'other factors', 'additional information',
        'for more information', 'as described in', 'further discussed in',
        'more fully described', 'conjunction with', 'forward-looking',
        'annual report on form'
    ]

    # Check element text for reference indicators
    element_lower = element_text.lower()
    if any(indicator in element_lower for indicator in reference_indicators):
        score -= 100  # Heavy penalty

    # Check parent text (if parent is small enough to be a single paragraph)
    parent = element.parent
    if parent:
        parent_text = parent.get_text(strip=True)
        if len(parent_text) < 500:  # Only check if parent is reasonably sized
            parent_lower = parent_text.lower()
            if any(indicator in parent_lower for indicator in reference_indicators):
                score -= 80

    # Check what comes AFTER this element - real headings have risk factor content after them
    next_content = []
    current = element.find_next()
    chars_collected = 0
    count = 0

    while current and count < 20 and chars_collected < 2000:
        if current.name in ['p', 'div', 'span', 'td']:
            next_text = current.get_text(strip=True)
            if next_text and len(next_text) > 10:
                next_content.append(next_text)
                chars_collected += len(next_text)
        current = current.find_next()
        count += 1

    combined_next = ' '.join(next_content).lower()

    # Check for risk factor keywords in following content
    risk_keywords = ['risk', 'uncertain', 'could', 'may', 'might',
                     'adverse', 'factor', 'subject to', 'depend', 'fail']
    risk_count = sum(
        1 for keyword in risk_keywords if keyword in combined_next)
    score += risk_count * 5  # Bonus for each risk keyword

    # Bonus for substantial content following
    if chars_collected > 1000:
        score += 30
    elif chars_collected > 500:
        score += 15

    # Check if next major item section appears (Item 1B, Item 2)
    # This validates we're in the right place in the document
    next_item_patterns = [
        r'\bITEM\s*1B\b',
        r'\bItem\s*1B\b',
        r'\bITEM\s*2\b',
        r'\bItem\s*2\b',
    ]

    if any(re.search(pattern, combined_next, re.IGNORECASE) for pattern in next_item_patterns):
        score += 20  # Bonus for having next section marker

    return score


def find_all_item1a_candidates(soup):
    """
    Find ALL potential Item 1A heading matches and score them.
    Returns list of (score, element) tuples sorted by score.
    """
    patterns = [
        r'^\s*ITEM\s*1A\.?\s*RISK\s*FACTORS\.?\s*$',
        r'^\s*Item\s*1A\.?\s*Risk\s*Factors\.?\s*$',
    ]

    candidates = []

    # Search through relevant elements
    for element in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'td']):
        text = element.get_text(strip=True)

        # Check if this matches any pattern
        for pattern in patterns:
            if re.match(pattern, text, re.IGNORECASE):
                score = score_candidate(element, text, soup)
                candidates.append((score, element, text))
                break  # Don't double-count

    # Sort by score (highest first)
    candidates.sort(key=lambda x: x[0], reverse=True)

    return candidates


def find_item1a_start(soup):
    """
    Find the start of Item 1A Risk Factors section by finding all candidates
    and selecting the best one.
    """
    candidates = find_all_item1a_candidates(soup)

    if not candidates:
        return None

    # Return the highest-scoring candidate
    best_score, best_element, best_text = candidates[0]

    # Only accept if score is positive (otherwise even best match is suspicious)
    if best_score > 0:
        return best_element

    return None


def find_next_major_section(element):
    """
    Find the next major section after Item 1A (like Item 1B, Item 2, etc.)
    """
    patterns = [
        r'^\s*ITEM\s*1B',
        r'^\s*Item\s*1B',
        r'^\s*ITEM\s*2[^0-9]',
        r'^\s*Item\s*2[^0-9]',
    ]

    current = element
    while current:
        current = current.find_next()
        if not current:
            break

        if current.name in ['p', 'div', 'span', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = current.get_text(strip=True)
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return current

    return None


def extract_item1a_content(soup):
    """Extract the content of Item 1A Risk Factors"""

    # Find start of Item 1A
    start_element = find_item1a_start(soup)
    if not start_element:
        return None

    # Find end (next major section)
    end_element = find_next_major_section(start_element)

    # Extract all text between start and end
    content_parts = []
    current = start_element.find_next()

    while current and current != end_element:
        if current.name in ['p', 'div', 'span', 'td', 'li']:
            text = current.get_text(separator=' ', strip=True)
            if text and len(text) > 10:  # Skip very short snippets
                # Check if this looks like a table of contents
                if not re.search(r'^\s*\d+\s*$', text) and 'Table of Contents' not in text:
                    content_parts.append(text)

        current = current.find_next()

    # Combine all parts
    full_text = ' '.join(content_parts)
    return clean_text(full_text)


def split_into_sentences(text):
    """
    Split text into sentences, handling bullet points
    """
    # First, identify bullet points and replace them with special markers
    text = re.sub(r'[•·▪]', '|||BULLET|||', text)

    # Split on bullet markers
    parts = text.split('|||BULLET|||')

    sentences = []
    for part in parts:
        if not part.strip():
            continue

        # Split on sentence endings, but be careful with abbreviations
        # Look for period/question mark/exclamation followed by space and capital letter or end of string
        sentence_endings = re.split(
            r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])$', part)

        for sent in sentence_endings:
            sent = sent.strip()
            if sent and len(sent) > 3:  # Skip very short fragments
                sentences.append(sent)

    return sentences


def format_output(sentences):
    """Format sentences according to requirements"""
    # Escape single quotes in sentences
    escaped_sentences = [s.replace("'", "\\'") for s in sentences]

    # Join with ', '
    output = "['" + "', '".join(escaped_sentences) + "']"

    return output


def process_file(input_path, output_path):
    """Process a single HTML file"""
    print(f"Processing {input_path.name}...")

    try:
        # Read HTML file
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()

        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract Item 1A content
        item1a_text = extract_item1a_content(soup)

        if not item1a_text:
            print(f"  ⚠ Could not find Item 1A section in {input_path.name}")
            return False

        # Split into sentences
        sentences = split_into_sentences(item1a_text)

        if not sentences:
            print(f"  ⚠ No sentences extracted from {input_path.name}")
            return False

        # Format output
        output_text = format_output(sentences)

        # Write to output file
        output_file = output_path / (input_path.stem + '.txt')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_text)

        print(
            f"  ✓ Extracted {len(sentences)} sentences to {output_file.name}")
        return True

    except Exception as e:
        print(f"  ✗ Error processing {input_path.name}: {str(e)}")
        return False


def main():
    """Main function"""
    # Define directories
    input_dir = Path('10k_html_2024')
    output_dir = Path('item1a_text_2024')

    # Check if input directory exists
    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' not found!")
        print("Please create the directory and add your HTML files.")
        return

    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)

    # Get all HTML files
    html_files = list(input_dir.glob('*.html')) + list(input_dir.glob('*.htm'))

    if not html_files:
        print(f"No HTML files found in {input_dir}")
        return

    print(f"Found {len(html_files)} HTML files\n")

    # Process each file
    success_count = 0
    for html_file in html_files:
        if process_file(html_file, output_dir):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"Successfully processed: {success_count}/{len(html_files)} files")
    print(f"Output directory: {output_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
