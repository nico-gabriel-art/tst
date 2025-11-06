"""
Extract Item 1A Risk Factors from 10-K HTML files
"""

import os
import re
from bs4 import BeautifulSoup
from pathlib import Path


def clean_text(text):
    """Clean extracted text"""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('\xa0', ' ')
    text = text.replace('\u200b', '')  # Remove zero-width spaces
    text = text.strip()
    return text


def is_likely_toc_reference(element, text):
    """Check if this is likely a table of contents reference"""
    # Check if followed by page numbers
    next_sibling = element.find_next_sibling()
    if next_sibling:
        next_text = next_sibling.get_text(strip=True)
        if re.match(r'^\d+$', next_text) or re.match(r'^\.+\d+$', next_text):
            return True
    
    # Check if very short with no following content
    parent = element.parent
    if parent and len(text) < 100:
        # Look for page numbers or dots in parent
        parent_text = parent.get_text()
        if re.search(r'\.{3,}|\d+\s*$', parent_text):
            return True
    
    return False


def get_section_content_score(start_element):
    """
    Score how likely this is the actual Risk Factors section
    Returns: (score, substantive_paragraphs)
    """
    score = 0
    paragraphs = []
    
    # Collect next 50 elements to analyze
    current = start_element.find_next()
    count = 0
    element_count = 0
    
    while current and element_count < 50:
        if current.name in ['p', 'div', 'td', 'li', 'span']:
            text = current.get_text(strip=True)
            if text and len(text) > 30:
                element_count += 1
                paragraphs.append(text)
                
                # Higher score for risk-related keywords
                if re.search(r'\b(risk|could|may|might|uncertain|adverse|fail|loss|damage|harm|negatively|materially)\b', text, re.IGNORECASE):
                    score += 2
                
                # Lower score for TOC-like content
                if re.search(r'^(ITEM|Item)\s+\d+[A-Z]?\.', text):
                    score -= 10  # Heavy penalty for other Item references
                    
                if re.search(r'\.{3,}|\d+\s*$', text):
                    score -= 5  # Penalty for dots/page numbers
                
                count += 1
                if count >= 10:
                    break
        
        current = current.find_next()
    
    # Bonus for having multiple substantial paragraphs
    if len(paragraphs) >= 5:
        score += 10
    
    # Check average paragraph length
    if paragraphs:
        avg_length = sum(len(p) for p in paragraphs) / len(paragraphs)
        if avg_length > 100:
            score += 5
    
    return score, paragraphs


def find_item1a_start(soup):
    """
    Find the start of Item 1A Risk Factors section with improved detection
    """
    # Patterns to match Item 1A headings
    patterns = [
        r'^\s*ITEM\s*1A\.?\s*[\-\u2014]?\s*RISK\s*FACTORS\.?\s*$',
        r'^\s*Item\s*1A\.?\s*[\-\u2014]?\s*Risk\s*Factors\.?\s*$',
        r'^\s*ITEM\s*1A\.?\s*$',
        r'^\s*Item\s*1A\.?\s*$',
        r'^\s*ITEM\s*1A\s*\.',
        r'^\s*Item\s*1A\s*\.',
    ]
    
    candidates = []
    
    # Search through all text elements
    for element in soup.find_all(['p', 'div', 'span', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'b', 'strong']):
        text = element.get_text(strip=True)
        
        # Check if this matches any pattern
        for pattern in patterns:
            if re.match(pattern, text, re.IGNORECASE):
                # Skip if it's likely a TOC reference
                if is_likely_toc_reference(element, text):
                    continue
                
                # Get score for this candidate
                score, paragraphs = get_section_content_score(element)
                
                # Only consider if we have decent content following
                if score > 0 and len(paragraphs) >= 3:
                    candidates.append({
                        'element': element,
                        'score': score,
                        'text': text,
                        'paragraphs': len(paragraphs)
                    })
    
    # Return the best candidate
    if candidates:
        best_candidate = max(candidates, key=lambda x: x['score'])
        if best_candidate['score'] > 5:  # Minimum threshold
            return best_candidate['element']
    
    return None


def get_next_section_score(element):
    """
    Score how likely this is an actual section header (not a reference)
    Returns: score
    """
    score = 0
    
    # Get the text of the element itself
    text = element.get_text(strip=True)
    
    # Short, standalone text is more likely to be a header
    if len(text) < 100:
        score += 10
    elif len(text) < 50:
        score += 15
    else:
        score -= 10  # Long text unlikely to be just a header
    
    # Check if it's in a heading tag
    if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        score += 20
    elif element.name in ['b', 'strong']:
        score += 10
    
    # Check if followed by substantial new content (not just another reference)
    next_elements = []
    current = element.find_next()
    count = 0
    
    while current and count < 20:
        if current.name in ['p', 'div', 'td', 'li']:
            next_text = current.get_text(strip=True)
            if next_text and len(next_text) > 30:
                next_elements.append(next_text)
                count += 1
                if count >= 5:
                    break
        current = current.find_next()
    
    # Check if what follows looks like a new section start
    if len(next_elements) >= 3:
        score += 10
        
        # Check average length of following content
        avg_length = sum(len(t) for t in next_elements) / len(next_elements)
        if avg_length > 80:
            score += 10
    
    # Penalty if this looks like a TOC reference
    if is_likely_toc_reference(element, text):
        score -= 30
    
    # Penalty if it contains more than just the item number and title
    # (likely a reference within text)
    words = text.split()
    if len(words) > 10:
        score -= 15
    
    return score


def find_next_major_section(element):
    """
    Find the next major section after Item 1A using scoring logic
    """
    patterns = [
        # Item 1B patterns
        r'^\s*ITEM\s*1B\.?\s*[\-\u2014]?\s*UNRESOLVED',
        r'^\s*Item\s*1B\.?\s*[\-\u2014]?\s*Unresolved',
        r'^\s*ITEM\s*1B\.?\s*[\-\u2014]?',
        r'^\s*Item\s*1B\.?\s*[\-\u2014]?',
        # Item 2 patterns
        r'^\s*ITEM\s*2\.?\s*[\-\u2014]?\s*PROPERTIES',
        r'^\s*Item\s*2\.?\s*[\-\u2014]?\s*Properties',
        r'^\s*ITEM\s*2\.?\s*[\-\u2014]?\s*DESCRIPTION',
        r'^\s*Item\s*2\.?\s*[\-\u2014]?\s*Description',
        r'^\s*ITEM\s*2\.?\s*[\-\u2014]?',
        r'^\s*Item\s*2\.?\s*[\-\u2014]?',
        # Item 1C patterns (less common but possible)
        r'^\s*ITEM\s*1C\.?\s*[\-\u2014]?',
        r'^\s*Item\s*1C\.?\s*[\-\u2014]?',
    ]
    
    candidates = []
    current = element
    distance = 0
    max_distance = 2000  # Prevent infinite loops
    
    while current and distance < max_distance:
        current = current.find_next()
        if not current:
            break
        
        distance += 1
        
        if current.name in ['p', 'div', 'span', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'b', 'strong']:
            text = current.get_text(strip=True)
            
            # Check if this matches any pattern
            for pattern in patterns:
                if re.match(pattern, text, re.IGNORECASE):
                    # Score this candidate
                    score = get_next_section_score(current)
                    
                    # Only consider if score is positive
                    if score > 0:
                        candidates.append({
                            'element': current,
                            'score': score,
                            'text': text,
                            'distance': distance
                        })
                    break  # Found a match for this element, move to next
    
    # Return the best candidate
    if candidates:
        # Prefer earlier candidates with good scores
        # Sort by score, but give slight preference to earlier occurrences
        best_candidate = max(candidates, key=lambda x: x['score'] - (x['distance'] * 0.01))
        
        # Only return if score is above threshold
        if best_candidate['score'] > 10:
            return best_candidate['element']
    
    return None


def extract_item1a_content(soup):
    """Extract the content of Item 1A Risk Factors"""
    
    # Find start of Item 1A
    start_element = find_item1a_start(soup)
    if not start_element:
        return None
    
    start_text = start_element.get_text(strip=True)
    print(f"    Found Item 1A start: '{start_text[:80]}...'")
    
    # Find end (next major section)
    end_element = find_next_major_section(start_element)
    
    if end_element:
        end_text = end_element.get_text(strip=True)
        print(f"    Found section end: '{end_text[:80]}...'")
    else:
        print(f"    Warning: No clear end section found, will extract until end of available content")
    
    # Extract all text between start and end
    content_parts = []
    current = start_element.find_next()
    
    # Track elements to avoid infinite loops
    seen_elements = set()
    max_iterations = 10000
    iterations = 0
    
    while current and current != end_element and iterations < max_iterations:
        iterations += 1
        
        # Avoid processing same element twice
        element_id = id(current)
        if element_id in seen_elements:
            break
        seen_elements.add(element_id)
        
        if current.name in ['p', 'div', 'span', 'td', 'li']:
            text = current.get_text(separator=' ', strip=True)
            if text and len(text) > 15:  # Minimum meaningful text length
                # Skip table of contents indicators
                if not re.search(r'^\s*\d+\s*$', text) and 'Table of Contents' not in text:
                    # Skip if it's another Item reference (false positive check)
                    # But allow "Item" if it's part of a longer sentence
                    if not re.match(r'^\s*ITEM\s+\d+[A-Z]?\b', text, re.IGNORECASE):
                        content_parts.append(text)
        
        current = current.find_next()
    
    print(f"    Extracted {len(content_parts)} text segments")
    
    # Combine all parts
    full_text = ' '.join(content_parts)
    return clean_text(full_text) if full_text else None


def split_into_sentences(text):
    """
    Split text into sentences, handling bullet points
    """
    # Replace bullet points with markers
    text = re.sub(r'[•·▪■●]', '|||BULLET|||', text)
    
    # Split on bullet markers
    parts = text.split('|||BULLET|||')
    
    sentences = []
    for part in parts:
        if not part.strip():
            continue
        
        # Split on sentence endings
        sentence_endings = re.split(
            r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])$', part)
        
        for sent in sentence_endings:
            sent = sent.strip()
            if sent and len(sent) > 3:
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
        
        # Check if we got meaningful content
        if len(item1a_text) < 500:
            print(f"  ⚠ Item 1A content too short in {input_path.name} ({len(item1a_text)} chars)")
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
        
        print(f"  ✓ Extracted {len(sentences)} sentences ({len(item1a_text)} chars) to {output_file.name}")
        return True
    
    except Exception as e:
        print(f"  ✗ Error processing {input_path.name}: {str(e)}")
        import traceback
        traceback.print_exc()
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
