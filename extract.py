"""
Extract Item 1A Risk Factors from 10-K HTML files
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


def find_item1a_start(soup):
    """
    Find the start of Item 1A Risk Factors section
    Returns the element where Item 1A starts
    """
    # Patterns to match Item 1A headings
    patterns = [
        r'^\s*ITEM\s*1A\.?\s*RISK\s*FACTORS\.?\s*$',
        r'^\s*Item\s*1A\.?\s*Risk\s*Factors\.?\s*$',
        r'^\s*ITEM\s*1A\s*$',
        r'^\s*Item\s*1A\s*$',
    ]

    # Search through all text elements
    for element in soup.find_all(['p', 'div', 'span', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        text = element.get_text(strip=True)

        # Check if this matches any pattern
        for pattern in patterns:
            if re.match(pattern, text, re.IGNORECASE):
                # Make sure this is not just a table of contents reference
                # Check if there's substantive content following
                next_elements = []
                current = element.find_next()
                count = 0
                while current and count < 10:
                    if current.name in ['p', 'div', 'span', 'td']:
                        next_text = current.get_text(strip=True)
                        if next_text and len(next_text) > 50:  # Substantive text
                            return element
                    current = current.find_next()
                    count += 1

    return None


def find_next_major_section(element):
    """
    Find the next major section after Item 1A (like Item 1B, Item 2, etc.)
    """
    patterns = [
        r'^\s*ITEM\s*1B',
        r'^\s*Item\s*1B',
        r'^\s*ITEM\s*2',
        r'^\s*Item\s*2',
    ]

    current = element
    while current:
        current = current.find_next()
        if not current:
            break

        if current.name in ['p', 'div', 'span', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            text = current.get_text(strip=True)
            for pattern in patterns:
                if re.match(pattern, text, re.IGNORECASE):
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
